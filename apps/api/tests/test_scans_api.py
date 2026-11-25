"""Scan tags and measurements: extraction, owner review, backfill, inbox hook. All data is synthetic."""
import datetime as dt

import pytest
from sqlmodel import select

from config import settings
from db.models import MedicalRecord, RecordAttachment, RecordOrgan, ScanMeasurement
from services import scan_store
from services.organs import ORIGINS, SIDES
from services.scan_extractor import Extraction, Measurement
from tests.pdf_factory import text_pdf

THYROID = """Thyroid gland ultrasound findings:
• Right lobe: 12×15×44 mm (5.2 cm³)
• Left lobe: 13×16×40 mm (5.0 cm³)
• Total volume: 10.2 cm³ (within normal range for male 57 kg)"""


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return tmp_path


def _imaging(session, title="Thyroid Ultrasound", details=THYROID):
    rec = MedicalRecord(record_type="imaging", title=title, details=details, record_date=dt.date(2024, 5, 1))
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def _by_key(body):
    return {(m["organ_key"], m["param_key"], m["side"]): m for m in body["measurements"]}


def _put_body(body, changes):
    rows = [{k: m[k] for k in ("organ_key", "param_key", "side", "value", "value_text")} for m in body["measurements"]]
    for row in rows:
        if (row["organ_key"], row["param_key"], row["side"]) in changes:
            row["value"] = changes[(row["organ_key"], row["param_key"], row["side"])]
    return {"organs": [o["organ_key"] for o in body["organs"]], "measurements": rows}


def test_extract_tags_and_stores_unverified(client, session):
    rec = _imaging(session)
    res = client.post(f"/api/v1/scans/{rec.id}/extract")
    assert res.status_code == 200
    body = res.json()
    assert [o["organ_key"] for o in body["organs"]] == ["thyroid"]
    assert body["report"]["added"] >= 3 and body["report"]["organs_added"] == ["thyroid"]
    assert body["measurements"] and all(m["verified"] is False and m["origin"] == "rule" for m in body["measurements"])
    assert _by_key(body)[("thyroid", "volume_total", "")]["value"] == pytest.approx(10.2)
    assert client.get(f"/api/v1/scans/{rec.id}").json()["measurements"] == body["measurements"]


def test_get_unknown_record_is_404(client):
    assert client.get("/api/v1/scans/999").status_code == 404
    assert client.put("/api/v1/scans/999", json={"organs": [], "measurements": []}).status_code == 404
    assert client.post("/api/v1/scans/999/extract").status_code == 404


def test_unreadable_record_has_no_tags_and_stays_untagged(client, session):
    rec = _imaging(session, title="Scan", details="Все в норме")
    body = client.post(f"/api/v1/scans/{rec.id}/extract").json()
    assert body["organs"] == [] and body["measurements"] == []
    assert scan_store.backfill(session)["untagged"] == [rec.id]


def test_put_review_marks_verified_and_manual_when_changed(client, session):
    rec = _imaging(session)
    body = client.post(f"/api/v1/scans/{rec.id}/extract").json()
    res = client.put(f"/api/v1/scans/{rec.id}", json=_put_body(body, {("thyroid", "volume_total", ""): 11.0}))
    assert res.status_code == 200
    rows = _by_key(res.json())
    assert all(m["verified"] for m in rows.values())
    assert rows[("thyroid", "volume_total", "")]["origin"] == "manual" and rows[("thyroid", "volume_total", "")]["value"] == 11.0
    assert rows[("thyroid", "volume_lobe", "right")]["origin"] == "rule"
    assert [(o["organ_key"], o["origin"]) for o in res.json()["organs"]] == [("thyroid", "rule")]


def test_put_replaces_rows_and_adds_manual_tag(client, session):
    rec = _imaging(session)
    client.post(f"/api/v1/scans/{rec.id}/extract")
    res = client.put(f"/api/v1/scans/{rec.id}", json={"organs": ["liver"], "measurements": [
        {"organ_key": "liver", "param_key": "echotexture", "value_text": "coarse"}]})
    body = res.json()
    assert [(o["organ_key"], o["origin"]) for o in body["organs"]] == [("liver", "manual")]
    assert [(m["param_key"], m["value_text"], m["origin"], m["verified"]) for m in body["measurements"]] == [
        ("echotexture", "coarse", "manual", True)]


def test_reextract_never_touches_verified_or_manual(client, session):
    rec = _imaging(session)
    body = client.post(f"/api/v1/scans/{rec.id}/extract").json()
    client.put(f"/api/v1/scans/{rec.id}", json=_put_body(body, {("thyroid", "volume_total", ""): 11.0}))
    # an unverified row of the same record that the new text will change
    session.add(ScanMeasurement(record_id=rec.id, organ_key="thyroid", param_key="nodule_max_mm", value=3.0, unit="mm"))
    rec.details = THYROID.replace("10.2 cm³", "20.2 cm³") + "\nDetected nodule 11×9 mm"
    session.add(rec)
    session.commit()
    res = client.post(f"/api/v1/scans/{rec.id}/extract").json()
    rows = _by_key(res)
    assert rows[("thyroid", "volume_total", "")]["value"] == 11.0 and rows[("thyroid", "volume_total", "")]["verified"]
    assert res["report"]["skipped_verified"] >= 1
    nodule = rows[("thyroid", "nodule_max_mm", "")]
    assert nodule["value"] == pytest.approx(11) and nodule["origin"] == "rule" and nodule["verified"] is False
    assert res["report"]["updated"] == 1


def test_backfill_is_idempotent_and_skips_touched_records(session):
    fresh = _imaging(session)
    tagged = _imaging(session)
    session.add(RecordOrgan(record_id=tagged.id, organ_key="liver", origin="manual"))
    other = MedicalRecord(record_type="lab", title="Thyroid", details=THYROID)
    session.add(other)
    session.commit()
    first = scan_store.backfill(session)
    assert first["records"] == 1 and first["tagged"] == 1 and first["measurements"] >= 3 and first["untagged"] == []
    assert session.exec(select(RecordOrgan).where(RecordOrgan.record_id == fresh.id)).one().organ_key == "thyroid"
    assert scan_store.backfill(session) == {"records": 0, "tagged": 0, "measurements": 0, "untagged": [], "errors": []}
    assert session.exec(select(ScanMeasurement).where(ScanMeasurement.record_id == tagged.id)).all() == []


@pytest.mark.parametrize("body", [
    {"organs": ["spine"], "measurements": []},
    {"organs": [], "measurements": [{"organ_key": "thyroid", "param_key": "nope", "value": 1}]},
    {"organs": [], "measurements": [{"organ_key": "thyroid", "param_key": "volume_total", "side": "left", "value": 1}]},
    {"organs": [], "measurements": [{"organ_key": "thyroid", "param_key": "volume_lobe", "side": "", "value": 1}]},
    {"organs": [], "measurements": [{"organ_key": "thyroid", "param_key": "volume_lobe", "side": "up", "value": 1}]},
    {"organs": [], "measurements": [{"organ_key": "thyroid", "param_key": "volume_total", "value": -1}]},
    {"organs": [], "measurements": [{"organ_key": "thyroid", "param_key": "volume_total", "value": 100001}]},
    {"organs": [], "measurements": [{"organ_key": "thyroid", "param_key": "volume_total"}]},
    {"organs": [], "measurements": [{"organ_key": "thyroid", "param_key": "volume_total", "value_text": "big"}]},
    {"organs": [], "measurements": [{"organ_key": "thyroid", "param_key": "echogenicity", "value": 3}]},
    {"organs": [], "measurements": [{"organ_key": "thyroid", "param_key": "volume_total", "value": 1},
                                    {"organ_key": "thyroid", "param_key": "volume_total", "value": 2}]},
])
def test_put_validation(client, session, body):
    rec = _imaging(session)
    en = client.put(f"/api/v1/scans/{rec.id}", json=body)
    ru = client.put(f"/api/v1/scans/{rec.id}", json=body, headers={"Accept-Language": "ru"})
    assert en.status_code == 422 and ru.status_code == 422
    assert en.json()["detail"] != ru.json()["detail"]
    assert session.exec(select(ScanMeasurement)).all() == []


def test_writers_enforce_side_and_origin_constants(session):
    assert SIDES == ("", "left", "right") and ORIGINS == ("rule", "ai", "manual")
    rec = _imaging(session)
    ex = Extraction(["thyroid"], [Measurement("thyroid", "volume_total", "", 1.0, None, "cm³")])
    with pytest.raises(ValueError):
        scan_store.apply_extraction(session, rec.id, ex, "robot")
    bad_side = Extraction(["thyroid"], [Measurement("thyroid", "volume_total", "middle", 1.0, None, "cm³")])
    report = scan_store.apply_extraction(session, rec.id, bad_side, "rule")
    assert report.added == 0
    with pytest.raises(scan_store.ScanInvalid):
        scan_store.replace_review(session, rec.id, [], [scan_store.MeasurementIn(
            organ_key="thyroid", param_key="volume_total", side="middle", value=1.0)])


def test_delete_record_removes_tags_and_measurements(client, session):
    rec = _imaging(session)
    client.post(f"/api/v1/scans/{rec.id}/extract")
    assert session.exec(select(ScanMeasurement)).all() and session.exec(select(RecordOrgan)).all()
    assert client.delete(f"/api/v1/records/{rec.id}").status_code == 204
    session.expire_all()
    assert session.exec(select(ScanMeasurement)).all() == [] and session.exec(select(RecordOrgan)).all() == []


def test_record_text_reads_pdf_attachments_and_never_raises(session, data_dir):
    rec = _imaging(session, details="found")
    pdf = text_pdf("Spleen length 11 cm")
    (data_dir / "attachments").mkdir()
    (data_dir / "attachments" / "a.pdf").write_bytes(pdf)
    (data_dir / "attachments" / "bad.pdf").write_bytes(b"%PDF-garbage")
    for name, stored in (("a.pdf", "attachments/a.pdf"), ("bad.pdf", "attachments/bad.pdf"), ("gone.pdf", "attachments/gone.pdf")):
        session.add(RecordAttachment(record_id=rec.id, filename=name, stored_path=stored, mime_type="application/pdf",
                                     size_bytes=1, sha256=name))
    session.commit()
    text = scan_store.record_text(session, rec)
    assert "found" in text and "Spleen length 11 cm" in text


def test_inbox_confirm_of_imaging_report_runs_rule_extraction(client, session):
    pdf = text_pdf("Thyroid Ultrasound", "Right lobe: 12x15x44 mm (5.2 cm3)", "Total volume: 10.2 cm3")
    h = client.post("/api/v1/inbox/analyze", files={"file": ("us.pdf", pdf, "application/pdf")}).json()["file_hash"]
    res = client.post("/api/v1/inbox/confirm", json={"items": [
        {"file_hash": h, "kind": "imaging_report", "filename": "us.pdf", "title": "Thyroid Ultrasound"}]})
    result = res.json()["results"][0]
    assert result["status"] == "saved"
    body = client.get(f"/api/v1/scans/{result['record_id']}").json()
    assert [o["organ_key"] for o in body["organs"]] == ["thyroid"]
    assert body["measurements"] and all(m["verified"] is False for m in body["measurements"])


def test_inbox_extraction_failure_does_not_fail_the_save(client, session, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr("services.inbox.run_rule_extraction", boom)
    pdf = text_pdf("Thyroid Ultrasound", "Total volume: 10.2 cm3")
    h = client.post("/api/v1/inbox/analyze", files={"file": ("us.pdf", pdf, "application/pdf")}).json()["file_hash"]
    result = client.post("/api/v1/inbox/confirm", json={"items": [{"file_hash": h, "kind": "imaging_report"}]}).json()["results"][0]
    assert result["status"] == "saved" and result["record_id"]


def test_inbox_imaging_file_attached_to_a_visit_does_not_tag_the_visit(client, session):
    visit = MedicalRecord(title="Visit", record_type="visit", record_date=dt.date(2024, 5, 1))
    session.add(visit)
    session.commit()
    session.refresh(visit)
    pdf = text_pdf("Thyroid Ultrasound", "Right lobe: 12x15x44 mm (5.2 cm3)", "Total volume: 10.2 cm3")
    h = client.post("/api/v1/inbox/analyze", files={"file": ("us.pdf", pdf, "application/pdf")}).json()["file_hash"]
    result = client.post("/api/v1/inbox/confirm", json={"items": [
        {"file_hash": h, "kind": "imaging_report", "record_id": visit.id}]}).json()["results"][0]
    assert result["status"] == "saved" and result["record_id"] == visit.id
    body = client.get(f"/api/v1/scans/{visit.id}").json()
    assert body["organs"] == [] and body["measurements"] == []


def test_inbox_imaging_file_attached_to_an_imaging_record_is_read(client, session):
    rec = _imaging(session, title="Ultrasound", details="")
    pdf = text_pdf("Thyroid Ultrasound", "Total volume: 10.2 cm3")
    h = client.post("/api/v1/inbox/analyze", files={"file": ("us.pdf", pdf, "application/pdf")}).json()["file_hash"]
    client.post("/api/v1/inbox/confirm", json={"items": [{"file_hash": h, "kind": "imaging_report", "record_id": rec.id}]})
    assert [o["organ_key"] for o in client.get(f"/api/v1/scans/{rec.id}").json()["organs"]] == ["thyroid"]


# ---- carry-over fixes ----

def test_put_value_text_is_stripped_and_capped(client, session):
    rec = _imaging(session)
    row = {"organ_key": "thyroid", "param_key": "echogenicity", "side": "", "value": None}
    ok = client.put(f"/api/v1/scans/{rec.id}", json={"organs": [], "measurements": [{**row, "value_text": "  decreased "}]})
    assert ok.status_code == 200 and ok.json()["measurements"][0]["value_text"] == "decreased"
    ok = client.put(f"/api/v1/scans/{rec.id}", json={"organs": [], "measurements": [{**row, "value_text": "x" * 200}]})
    assert ok.status_code == 200
    long = client.put(f"/api/v1/scans/{rec.id}", json={"organs": [], "measurements": [{**row, "value_text": "x" * 201}]})
    assert long.status_code == 422
    assert long.json()["detail"] == client.put(
        f"/api/v1/scans/{rec.id}", json={"organs": [], "measurements": [{**row, "value_text": "  "}]}).json()["detail"]


def test_backfill_continues_past_a_failing_record(session, monkeypatch):
    good1, bad, good2 = _imaging(session), _imaging(session, title="Bad Ultrasound"), _imaging(session)
    real = scan_store.run_rule_extraction

    def flaky(sess, record_id):
        if record_id == bad.id:
            sess.add(RecordOrgan(record_id=record_id, organ_key="thyroid", origin="rule"))  # a partial write
            raise RuntimeError("boom")
        return real(sess, record_id)
    monkeypatch.setattr(scan_store, "run_rule_extraction", flaky)
    out = scan_store.backfill(session)
    assert out["errors"] == [bad.id]
    assert out["records"] == 2 and out["tagged"] == 2 and set(out) >= {"records", "tagged", "measurements", "untagged"}
    assert session.exec(select(RecordOrgan).where(RecordOrgan.record_id == bad.id)).all() == []
    assert {t.record_id for t in session.exec(select(RecordOrgan))} == {good1.id, good2.id}


def test_backfill_script_never_creates_tables(tmp_path, capsys):
    import scripts.backfill_scans as script
    from sqlmodel import create_engine
    path = tmp_path / "old.db"
    create_engine(f"sqlite:///{path}").dispose()  # an empty database file
    assert script.main(["--db", str(path)]) != 0
    assert "alembic upgrade head" in capsys.readouterr().err
    from sqlalchemy import inspect
    assert inspect(create_engine(f"sqlite:///{path}")).get_table_names() == []


def test_backfill_script_runs_on_a_migrated_database(tmp_path, capsys):
    import scripts.backfill_scans as script
    from sqlmodel import SQLModel, Session, create_engine
    path = tmp_path / "new.db"
    engine = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        _imaging(s)
    assert script.main(["--db", str(path)]) == 0
    assert '"records": 1' in capsys.readouterr().out
