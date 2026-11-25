"""Opt-in AI extraction for scans, and the synthetic demo organ scans. All data is synthetic."""
import datetime as dt

import pytest
from sqlmodel import select

from config import settings
from db.models import (
    MedicalRecord, Medication, RecordAttachment, RecordMedication, RecordOrgan, ScanMeasurement,
)
from main import app
from routers.scans import get_scan_extractor_factory
from services.ai_provider import AiNotConfigured, build_scan_extractor
from services.demo_data import demo_counts, remove_demo, seed_demo
from services.gemini_client import AiRequestError
from services.scan_extractor import ScanExtractor

REPORT = "Thyroid gland ultrasound. The gland is homogeneous."


@pytest.fixture(autouse=True)
def fake_ai(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "biostack_fake_ai", True)
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    yield
    app.dependency_overrides.pop(get_scan_extractor_factory, None)


def _imaging(session, title="Ultrasound", details=REPORT):
    rec = MedicalRecord(record_type="imaging", title=title, details=details, record_date=dt.date(2024, 5, 1))
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def _by_key(body):
    return {(m["organ_key"], m["param_key"], m["side"]): m for m in body["measurements"]}


def test_ai_extract_validates_and_converts(client, session):
    rec = _imaging(session)
    res = client.post(f"/api/v1/scans/{rec.id}/extract?ai=1")
    assert res.status_code == 200
    got = _by_key(res.json())
    assert got[("thyroid", "volume_total", "")]["value"] == pytest.approx(10.5)
    assert got[("kidneys", "length_cm", "left")]["value"] == pytest.approx(9.8)  # 98 mm -> cm
    assert all(m["param_key"] != "made_up" for m in res.json()["measurements"])
    assert all(m["origin"] == "ai" and m["verified"] is False for m in res.json()["measurements"])
    assert {o["organ_key"] for o in res.json()["organs"]} == {"thyroid", "kidneys"}


def test_ai_does_not_override_verified(client, session):
    rec = _imaging(session)
    session.add(ScanMeasurement(record_id=rec.id, organ_key="thyroid", param_key="volume_total", value=7.0,
                                unit="cm³", origin="manual", verified=True))
    session.commit()
    body = client.post(f"/api/v1/scans/{rec.id}/extract?ai=1").json()
    assert _by_key(body)[("thyroid", "volume_total", "")]["value"] == 7.0
    assert _by_key(body)[("thyroid", "volume_total", "")]["verified"] is True


def test_ai_fills_only_the_remainder_after_rules(client, session):
    rec = _imaging(session, title="Thyroid Ultrasound", details="Thyroid gland:\nTotal volume: 9.0 cm³")
    body = client.post(f"/api/v1/scans/{rec.id}/extract?ai=1").json()
    row = _by_key(body)[("thyroid", "volume_total", "")]
    assert row["value"] == 9.0 and row["origin"] == "rule"
    assert _by_key(body)[("kidneys", "length_cm", "left")]["origin"] == "ai"


def test_ai_not_configured_is_503_localized(client, session, monkeypatch):
    monkeypatch.setattr(settings, "biostack_fake_ai", False)
    monkeypatch.setattr(settings, "gemini_api_key", "")
    rec = _imaging(session)
    en = client.post(f"/api/v1/scans/{rec.id}/extract?ai=1")
    assert en.status_code == 503 and "GEMINI_API_KEY" in en.json()["detail"]
    ru = client.post(f"/api/v1/scans/{rec.id}/extract?ai=1", headers={"Accept-Language": "ru"})
    assert ru.status_code == 503 and "Чтобы включить" in ru.json()["detail"]


def test_ai_not_configured_writes_nothing(client, session, monkeypatch):
    """A 503 must not leave rule rows behind: the page would keep its old draft and delete them on the next Save."""
    monkeypatch.setattr(settings, "biostack_fake_ai", False)
    monkeypatch.setattr(settings, "gemini_api_key", "")
    rec = _imaging(session, title="Thyroid Ultrasound", details="Thyroid gland:\nTotal volume: 9.0 cm³")
    assert client.post(f"/api/v1/scans/{rec.id}/extract?ai=1").status_code == 503
    session.expire_all()
    assert session.exec(select(ScanMeasurement).where(ScanMeasurement.record_id == rec.id)).all() == []
    assert session.exec(select(RecordOrgan).where(RecordOrgan.record_id == rec.id)).all() == []


def test_extract_without_ai_flag_never_calls_ai(client, session):
    def boom():
        raise AssertionError("AI must not be built")
    app.dependency_overrides[get_scan_extractor_factory] = lambda: boom
    rec = _imaging(session)
    assert client.post(f"/api/v1/scans/{rec.id}/extract").status_code == 200
    assert client.post(f"/api/v1/scans/{rec.id}/extract?ai=0").status_code == 200


class _Client:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, []

    def generate_json(self, prompt, document, schema, mime_type="application/pdf"):
        self.calls.append((prompt, document, mime_type))
        if self.error:
            raise self.error
        return self.answer


def _use(extractor_client):
    app.dependency_overrides[get_scan_extractor_factory] = lambda: (lambda: ScanExtractor(extractor_client))


def test_ai_failures_are_502_and_keep_rule_results(client, session):
    rec = _imaging(session, title="Thyroid Ultrasound", details="Thyroid gland:\nTotal volume: 9.0 cm³")
    _use(_Client(error=AiRequestError("The AI service returned an empty answer.")))
    assert client.post(f"/api/v1/scans/{rec.id}/extract?ai=1").status_code == 502
    _use(_Client(answer={"measurements": "nope"}))
    assert client.post(f"/api/v1/scans/{rec.id}/extract?ai=1").status_code == 502
    assert client.get(f"/api/v1/scans/{rec.id}").json()["measurements"][0]["origin"] == "rule"


def test_text_is_sent_when_present_else_the_first_attachment(client, session):
    rec = _imaging(session)
    fake = _Client({"measurements": []})
    _use(fake)
    client.post(f"/api/v1/scans/{rec.id}/extract?ai=1")
    prompt, doc, mime = fake.calls[0]
    assert REPORT.encode() in doc and mime == "text/plain"
    assert "kidneys" in prompt and "length_cm" in prompt  # the catalog is in the prompt

    bare = _imaging(session, details="")
    png = b"\x89PNG fake photo"
    (settings.data_dir / "a.png").write_bytes(png)
    session.add(RecordAttachment(record_id=bare.id, filename="a.png", stored_path="a.png", mime_type="image/png",
                                 size_bytes=len(png), sha256="x"))
    session.commit()
    fake.calls.clear()
    client.post(f"/api/v1/scans/{bare.id}/extract?ai=1")
    assert fake.calls and fake.calls[0][1] == png and fake.calls[0][2] == "image/png"


def test_extractor_drops_non_finite_and_bad_rows():
    rows = [
        {"organ": "thyroid", "param": "volume_total", "side": "", "value": float("nan"), "unit": "cm3", "text": None},
        {"organ": "nowhere", "param": "volume_total", "side": "", "value": 1, "unit": "cm3", "text": None},
        {"organ": "kidneys", "param": "length_cm", "side": "", "value": 10, "unit": "cm", "text": None},
        {"organ": "thyroid", "param": "volume_total", "side": "", "value": 5, "unit": "kg", "text": None},
        {"organ": "thyroid", "param": "tirads", "side": "", "value": 4, "unit": None, "text": None},
        {"organ": "thyroid", "param": "echogenicity", "side": "", "value": None, "unit": None, "text": " decreased "},
    ]
    out = ScanExtractor(_Client({"measurements": rows})).extract("Thyroid", "text", None, None)
    assert [(m.param_key, m.value, m.value_text) for m in out.measurements] == [
        ("tirads", 4.0, None), ("echogenicity", None, "decreased")]


def test_build_scan_extractor_needs_configuration():
    from config import Settings
    with pytest.raises(AiNotConfigured, match="GEMINI_API_KEY"):
        build_scan_extractor(Settings(_env_file=None, gemini_api_key="", gemini_model="m"))


# ---- demo data ----

TODAY = dt.date(2026, 3, 10)


def _scan_rows(session):
    return session.exec(select(ScanMeasurement)).all(), session.exec(select(RecordOrgan)).all()


def test_seed_demo_creates_organ_scans_and_cleanup_removes_them(session):
    seed_demo(session, TODAY)
    records = session.exec(select(MedicalRecord)).all()
    assert all(r.source == "demo" for r in records)
    thyroid = [r for r in records if r.title.startswith("Thyroid")]
    kidney = [r for r in records if r.title.startswith("Kidney")]
    assert len(thyroid) == 5 and len(kidney) == 2
    assert 2022 <= min(r.record_date.year for r in thyroid) and max(r.record_date for r in thyroid) <= TODAY
    rows, tags = _scan_rows(session)
    assert rows and all(r.origin in ("manual", "rule") for r in rows)
    assert {True, False} <= {r.verified for r in rows}
    vol = sorted((r.record_id, r.value) for r in rows if r.param_key == "volume_total")
    by_date = {r.id: r.record_date for r in thyroid}
    series = [v for _, v in sorted(vol, key=lambda p: by_date[p[0]])]
    assert series == sorted(series) and series[0] < series[-1]
    tirads = [r.value for r in sorted((r for r in rows if r.param_key == "tirads"), key=lambda r: by_date[r.record_id])]
    assert tirads[0] == 3 and tirads[-1] == 4
    assert {t.organ_key for t in tags} == {"thyroid", "kidneys"}
    course = session.exec(select(Medication)).all()
    assert [m.target_marker_key for m in course] == ["tsh"] and course[0].source == "demo"
    assert demo_counts(session)["MedicalRecord"] == 7

    remove_demo(session)
    for table in (MedicalRecord, Medication, ScanMeasurement, RecordOrgan, RecordMedication):
        assert session.exec(select(table)).all() == [], table.__name__


def test_demo_cleanup_leaves_real_records_and_their_scans_alone(session):
    real = MedicalRecord(title="Kidney ultrasound", record_type="imaging", source="manual")
    session.add(real)
    session.commit()
    session.add(RecordOrgan(record_id=real.id, organ_key="kidneys"))
    session.add(ScanMeasurement(record_id=real.id, organ_key="kidneys", param_key="length_cm", side="left", value=10.0,
                                unit="cm"))
    session.commit()
    seed_demo(session, TODAY)
    seed_demo(session, TODAY)  # reseeding replaces, never duplicates
    assert demo_counts(session)["MedicalRecord"] == 7
    remove_demo(session)
    assert [r.id for r in session.exec(select(MedicalRecord))] == [real.id]
    assert len(session.exec(select(ScanMeasurement)).all()) == 1 and len(session.exec(select(RecordOrgan)).all()) == 1


def test_demo_cleanup_removes_what_the_owner_added_to_demo_records(session):
    from db.models import Diagnosis
    seed_demo(session, TODAY)
    rec = session.exec(select(MedicalRecord)).first()
    session.add(Diagnosis(record_id=rec.id, name="x"))
    session.commit()
    remove_demo(session)
    assert session.exec(select(Diagnosis)).all() == []
