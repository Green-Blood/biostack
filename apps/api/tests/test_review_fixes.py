"""Regression tests for the verified review findings (C1, C2, I1, I3-I6, I8, M2, M3, M6)."""
import datetime as dt
import logging

import pytest
from sqlmodel import select

from config import settings
from db.models import Biomarker, LabReport, MarkerTier, Medication
from services import clock
from services.briefing import fallback_bullets, get_briefing
from services.briefing_writer import BriefingWriter
from services.clock import local_zone
from services.i18n import msg_plural, plural_category
from services.lab_rows import ReviewedRow, TierBand
from services.lab_store import save_report
from services.lab_text_parser import parse_lab_text, parse_tier_line

TODAY = dt.date(2026, 6, 1)
ZONE = local_zone()
NOW = dt.datetime(2026, 6, 1, 12, 0, tzinfo=ZONE).astimezone(dt.timezone.utc)
RU = {"Accept-Language": "ru"}
BANDS = [TierBand(tier="insufficient", min=10, max=29), TierBand(tier="normal", min=30, max=100)]


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda zone=None: TODAY)


def _result(session, on, value, unit="ng/mL", key="vitamin_d_25_oh", name="Vitamin D (25-OH)", ref=(None, None), tiers=None):
    report = save_report(session, test_date=on, lab_name="", source="manual", rows=[
        ReviewedRow(name=name, value=value, unit=unit, ref_min=ref[0], ref_max=ref[1], tiers=tiers or [])])
    return report


def _course(session, start="2026-03-01", end="2026-03-30", key="vitamin_d_25_oh", name="D3"):
    course = Medication(name=name, start_date=dt.date.fromisoformat(start), end_date=dt.date.fromisoformat(end) if end else None,
                        target_marker_key=key, source="manual")
    session.add(course)
    session.commit()
    session.refresh(course)
    return course


# ---- C1

def test_c1_list_hides_tiers_in_another_unit_and_history_labels_them(client, session):
    old = _result(session, dt.date(2025, 1, 1), 27.0, tiers=BANDS)
    _result(session, dt.date(2025, 6, 1), 75.0, unit="nmol/L")
    rows = {r["marker_key"]: r for r in client.get("/api/v1/biomarkers").json()}
    assert rows["vitamin_d_25_oh"]["unit"] == "nmol/L" and rows["vitamin_d_25_oh"]["tiers"] == []
    tiers = client.get("/api/v1/biomarkers/vitamin_d_25_oh/history").json()["tiers"]
    assert [t["unit"] for t in tiers] == ["ng/mL", "ng/mL"] and {t["report_id"] for t in tiers} == {old.id}


def test_c1_list_keeps_compatible_tiers_with_unit_and_report(client, session):
    report = _result(session, dt.date(2026, 5, 20), 27.0, unit="ng/ml", tiers=BANDS)
    tiers = {r["marker_key"]: r for r in client.get("/api/v1/biomarkers").json()}["vitamin_d_25_oh"]["tiers"]
    assert tiers[0] == {"tier": "insufficient", "min": 10.0, "max": 29.0, "label": "", "unit": "ng/mL", "report_id": report.id}


def test_c1_range_for_ignores_tiers_in_other_units():
    from services.courses import _range_for

    row = Biomarker(report_id=1, marker_key="k", display_name="k", value=75, unit="nmol/L")
    tiers = [{"tier": "normal", "min": 30.0, "max": 100.0, "label": "", "unit": "ng/mL", "report_id": 1}]
    assert _range_for(row, tiers) == (None, None)
    row.unit = "ng/ml"
    assert _range_for(row, tiers) == (30.0, 100.0)


# ---- C2 / I5

def test_c2_effect_across_units_is_a_mismatch_without_delta(client, session):
    _result(session, dt.date(2026, 2, 20), 20.0, unit="ng/mL")
    _result(session, dt.date(2026, 4, 5), 75.0, unit="nmol/L")
    cid = _course(session).id
    e = client.get(f"/api/v1/courses/{cid}/effect").json()
    assert e["state"] == "unit_mismatch"
    assert e["before"] == {"date": "2026-02-20", "value": 20.0, "unit": "ng/mL"}
    assert e["after"] == {"date": "2026-04-05", "value": 75.0, "unit": "nmol/L"}
    assert e["delta_abs"] is None and e["delta_pct"] is None and e["toward_range"] is None and e["stayed_in_range"] is None
    assert "unit" in e["note"].lower() or "unit" in client.get(f"/api/v1/courses/{cid}/effect").json()["note"].lower()
    ru = client.get(f"/api/v1/courses/{cid}/effect", headers=RU).json()["note"]
    assert "единиц" in ru


def test_i5_effect_reports_stayed_in_range(client, session):
    _result(session, dt.date(2026, 2, 20), 40.0, ref=(30, 100))
    _result(session, dt.date(2026, 4, 5), 50.0, ref=(30, 100))
    e = client.get(f"/api/v1/courses/{_course(session).id}/effect").json()
    assert e["state"] == "measured" and e["toward_range"] is None and e["stayed_in_range"] is True


def test_i5_stayed_in_range_false_when_outside(client, session):
    _result(session, dt.date(2026, 2, 20), 20.0, ref=(30, 100))
    _result(session, dt.date(2026, 4, 5), 45.0, ref=(30, 100))
    assert client.get(f"/api/v1/courses/{_course(session).id}/effect").json()["stayed_in_range"] is False


# ---- I8

def test_i8_open_ended_course_waits_for_the_retest_interval(client, session):
    _result(session, dt.date(2026, 2, 20), 20.0, ref=(30, 100))
    _result(session, dt.date(2026, 3, 3), 25.0, ref=(30, 100))  # 2 days in: too early
    cid = _course(session, end=None).id
    e = client.get(f"/api/v1/courses/{cid}/effect").json()
    assert e["state"] == "waiting_for_retest" and e["after"] is None and e["retest_due_date"] == "2026-05-30"
    _result(session, dt.date(2026, 5, 30), 45.0, ref=(30, 100))  # start + 90 days
    e = client.get(f"/api/v1/courses/{cid}/effect").json()
    assert e["state"] == "measured" and e["after"]["date"] == "2026-05-30"


def test_i8_open_ended_default_interval_is_28_days(client, session):
    _result(session, dt.date(2026, 2, 20), 5.0, key="unmapped:zzz", name="Zzz marker")
    key = session.exec(select(Biomarker)).first().marker_key
    _result(session, dt.date(2026, 3, 20), 7.0, name="Zzz marker")
    cid = _course(session, end=None, key=key).id
    e = client.get(f"/api/v1/courses/{cid}/effect").json()
    assert e["state"] == "waiting_for_retest" and e["retest_due_date"] == "2026-03-29"


# ---- M2

def test_m2_result_on_course_end_day_counts_as_after_in_freshness(client, session):
    _result(session, dt.date(2026, 5, 25), 40.0)
    _course(session, start="2026-05-01", end="2026-05-25")
    item = next(i for i in client.get("/api/v1/freshness").json()["items"] if i["marker_key"] == "vitamin_d_25_oh")
    assert item["course_id"] is None and item["reason"] == "interval"


# ---- M3

def test_m3_biomarker_age_uses_the_pinned_clock(client, session):
    _result(session, TODAY - dt.timedelta(days=10), 40.0)
    row = client.get("/api/v1/biomarkers").json()[0]
    assert row["age_days"] == 10


# ---- I1

def test_i1_tier_words_only_match_the_start_of_the_label():
    assert parse_tier_line("Highly sensitive CRP: 1.0 - 3.0 mg/l") is None
    assert parse_tier_line("Prediabetes high risk: 5,7 - 6,4 %") is None
    assert parse_tier_line("High: 5 - 9 mg/l").tier == "high"
    assert parse_tier_line("Elevated: 5 - 9 mg/l").tier == "high"
    assert parse_tier_line("Deficiency: 1 - 9 mg/l").tier == "deficient"
    assert parse_tier_line("Toxic: > 100 mg/l").tier == "toxic"
    assert parse_tier_line("повышенное содержание: > 50 ng/ml").tier == "high"
    assert parse_tier_line("Риск повышенный: 5 - 9") is None


def test_i1_lines_after_a_row_do_not_become_tiers():
    text = ("РЕЗУЛЬТАТЫ\nНорма Ед\nС-реактивный белок 1,2 0-5 mg/l\nHighly sensitive CRP: 1.0 - 3.0 mg/l\n"
            "Prediabetes high risk: 5,7 - 6,4 %\n")
    parsed = parse_lab_text(text)
    assert parsed is not None and parsed.rows[0].tiers == []


def test_i1_band_with_a_different_printed_unit_is_ignored():
    text = ("РЕЗУЛЬТАТЫ\nНорма Ед\nВитамин D 27,6 30-100 ng/ml\nнедостаточность: 10 - 29 ng/ml\n"
            "повышенное: 250 - 400 nmol/l\nнормальное состояние: 30 - 100 ng/ml\n")
    parsed = parse_lab_text(text)
    assert [t.tier for t in parsed.rows[0].tiers] == ["insufficient", "normal"]


# ---- I3

class _Counting:
    calls = 0

    def generate_json(self, prompt, document, schema, mime_type="application/pdf"):
        _Counting.calls += 1
        return {"bullets": ["a", "b", "c"]}


def test_i3_switching_language_does_not_invalidate_the_briefing_cache(session):
    _Counting.calls = 0
    _result(session, dt.date(2026, 1, 1), 10.0, ref=(30, 100))  # out of range and stale: its name is in the stamp
    _course(session, start="2026-05-20", end=None)
    for lang in ("ru", "en", "ru"):
        get_briefing(session, NOW, "23:00", ZONE, lambda: BriefingWriter(_Counting()), ai_enabled=True, lang=lang)
    assert _Counting.calls == 1


# ---- I4

def test_i4_rollback_after_attach_failure_leaves_no_tiers(client, session, tmp_path, monkeypatch):
    from services import inbox
    from tests.pdf_factory import text_pdf

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    pdf = text_pdf("Date 2025-03-04", "Test Result Reference Unit", "Ferritin 12 30-400 ng/ml")
    h = client.post("/api/v1/inbox/analyze", files={"file": ("f.pdf", pdf, "application/octet-stream")}).json()["file_hash"]
    row = {"name": "Ferritin", "value": 12, "unit": "ng/ml", "ref_min": 30, "ref_max": 400,
           "tiers": [{"tier": "normal", "min": 30, "max": 400, "label": "n"}, {"tier": "high", "min": 400, "label": "h"}]}
    item = {"file_hash": h, "kind": "lab", "test_date": "2025-03-04", "rows": [row]}
    real = inbox.attach_file

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(inbox, "attach_file", boom)
    result = client.post("/api/v1/inbox/confirm", json={"items": [item]}).json()["results"][0]
    assert result["status"] == "error"
    session.expire_all()
    assert session.exec(select(MarkerTier)).all() == [] and session.exec(select(LabReport)).all() == []
    monkeypatch.setattr(inbox, "attach_file", real)
    ok = client.post("/api/v1/inbox/confirm", json={"items": [{**item, "rows": [{**row, "tiers": []}]}]}).json()["results"][0]
    assert ok["status"] == "saved"
    session.expire_all()
    assert session.exec(select(MarkerTier).where(MarkerTier.report_id == ok["report_id"])).all() == []


# ---- I6

def test_i6_access_log_filter_redacts_the_search_query():
    from services.log_redaction import RedactSearchQuery

    def record(path):
        return logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                                 ("127.0.0.1:1", "GET", path, "1.1", 200), None)

    rec = record("/api/v1/search?q=my%20diagnosis&limit=6")
    assert RedactSearchQuery().filter(rec) is True
    assert rec.args[2] == "/api/v1/search?q=<redacted>" and "diagnosis" not in rec.getMessage()
    other = record("/api/v1/biomarkers?x=1")
    RedactSearchQuery().filter(other)
    assert other.args[2] == "/api/v1/biomarkers?x=1"
    bare = record("/api/v1/search")
    RedactSearchQuery().filter(bare)
    assert bare.args[2] == "/api/v1/search"


def test_i6_filter_is_installed_on_the_uvicorn_access_logger():
    import main  # noqa: F401
    from services.log_redaction import RedactSearchQuery

    assert any(isinstance(f, RedactSearchQuery) for f in logging.getLogger("uvicorn.access").filters)


# ---- M6

@pytest.mark.parametrize("n, ru, en", [(1, "one", "one"), (2, "few", "many"), (4, "few", "many"), (5, "many", "many"),
                                       (11, "many", "many"), (12, "many", "many"), (21, "one", "many"), (22, "few", "many"),
                                       (111, "many", "many"), (0, "many", "many")])
def test_m6_plural_categories(n, ru, en):
    assert plural_category("ru", n) == ru and plural_category("en", n) == en


def test_m6_stale_bullet_plurals():
    assert msg_plural("en", "briefing.stale_results", 1).startswith("1 result is older")
    assert msg_plural("en", "briefing.stale_results", 3).startswith("3 results are older")
    assert "1 результат " in msg_plural("ru", "briefing.stale_results", 1)
    assert "2 результата " in msg_plural("ru", "briefing.stale_results", 2)
    assert "5 результатов " in msg_plural("ru", "briefing.stale_results", 5)
    ctx = {"risk": {"score": None, "recommendations": []}, "correlations": [], "caffeine_left_at_tonights_bedtime_mg": 0,
           "data_age": [{"stale": True}], "courses": []}
    assert any(b.startswith("1 result is older") for b in fallback_bullets(ctx, "en"))
