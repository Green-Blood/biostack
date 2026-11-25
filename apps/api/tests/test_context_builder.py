import datetime as dt
import json

from db.models import (
    Biomarker, CnsTest, CorrelationCache, DailyMetric, EnvironmentalLog, HealthJournal, LabReport, SupplementLog,
)
from services.clock import local_zone
from services.context_builder import build_context

ZONE = local_zone()
NOW = dt.datetime(2026, 3, 10, 12, 0, tzinfo=ZONE).astimezone(dt.timezone.utc)
TODAY = NOW.astimezone(ZONE).date()


def _ago(hours: float) -> dt.datetime:
    return NOW - dt.timedelta(hours=hours)


def _context(session) -> dict:
    return build_context(session, NOW, "23:00", ZONE)


def test_an_empty_database_gives_empty_sections(session):
    context = _context(session)
    for section in ("daily_metrics", "supplements", "symptoms", "cns_tests", "environment", "correlations", "out_of_range_biomarkers"):
        assert context[section] == []
    assert context["risk"]["score"] is None and context["window_hours"] == 72


def test_only_the_trailing_72_hours_are_included(session):
    session.add(SupplementLog(timestamp=_ago(10), item_name="Caffeine", dosage=100, unit="mg", category="stimulant"))
    session.add(SupplementLog(timestamp=_ago(80), item_name="Magnesium", category="supplement"))
    session.add(CnsTest(timestamp=_ago(5), tap_count_10s=50, baseline_dev_pct=4.0))
    session.add(CnsTest(timestamp=_ago(100), tap_count_10s=45))
    session.add(DailyMetric(metric_date=TODAY, hrv_sdnn=55.0))
    session.add(DailyMetric(metric_date=TODAY - dt.timedelta(days=9), hrv_sdnn=30.0))
    session.commit()
    context = _context(session)
    assert [s["item"] for s in context["supplements"]] == ["Caffeine"]
    assert [t["taps"] for t in context["cns_tests"]] == [50]
    assert [m["date"] for m in context["daily_metrics"]] == [TODAY.isoformat()]


def test_symptoms_carry_only_a_date_and_a_severity(session):
    session.add(HealthJournal(entry_date=TODAY, category="symptom", title="Headache", description="private details",
                              severity_1_10=6, body_location="head"))
    session.add(HealthJournal(entry_date=TODAY, category="doctor_visit", title="Dr Smith", description="secret",
                              severity_1_10=None, body_location="knee"))
    session.commit()
    context = _context(session)
    assert context["symptoms"] == [{"date": TODAY.isoformat(), "severity": 6}]
    text = json.dumps(context)
    for private in ("Headache", "private details", "Dr Smith", "secret", "head", "knee", "journal"):
        assert private not in text


def test_top_correlations_are_listed_strongest_first(session):
    for i, p in enumerate((0.04, 0.001, 0.01, 0.03, 0.02, 0.005)):
        session.add(CorrelationCache(target_metric="hrv_sdnn", trigger_key=f"t{i}", correlation_score=-0.6, lag_hours=24,
                                     confidence_pct=round((1 - p) * 100, 1), p_value=p, n_days=30))
    session.commit()
    triggers = [c["trigger"] for c in _context(session)["correlations"]]
    assert triggers == ["t1", "t5", "t2", "t4", "t3"]


def test_latest_out_of_range_biomarkers_only(session):
    old = LabReport(test_date=dt.date(2024, 1, 1))
    new = LabReport(test_date=dt.date(2026, 1, 1))
    session.add_all([old, new])
    session.commit()
    session.add(Biomarker(report_id=old.id, marker_key="vitd", display_name="Vitamin D", value=12, unit="ng/mL", ref_min=30, ref_max=100, is_out_of_range=True))
    session.add(Biomarker(report_id=new.id, marker_key="vitd", display_name="Vitamin D", value=35, unit="ng/mL", ref_min=30, ref_max=100))
    session.add(Biomarker(report_id=new.id, marker_key="ferritin", display_name="Ferritin", value=10, unit="ng/mL", ref_min=30, ref_max=400, is_out_of_range=True))
    session.commit()
    names = [b["name"] for b in _context(session)["out_of_range_biomarkers"]]
    assert names == ["Ferritin"]


def test_environment_rows_and_caffeine_at_bedtime_are_included(session):
    session.add(EnvironmentalLog(timestamp=_ago(3), pm2_5=12.0, pressure_mmHg=760.0, pressure_delta_24h=-3.0))
    session.add(SupplementLog(timestamp=_ago(4), item_name="Caffeine", dosage=200, category="stimulant"))
    session.commit()
    context = _context(session)
    assert context["environment"][0]["pressure_delta_24h"] == -3.0
    assert context["caffeine_left_at_tonights_bedtime_mg"] > 0


def test_context_is_plain_json(session):
    session.add(DailyMetric(metric_date=TODAY, hrv_sdnn=55.0))
    session.commit()
    json.dumps(_context(session))


def test_profile_is_left_out_when_nothing_is_set(session):
    assert "profile" not in _context(session)


def test_profile_carries_exactly_the_allowed_fields_and_no_birth_date(session, monkeypatch):
    from db.models import BodyMeasurement, Profile
    from services import clock

    monkeypatch.setattr(clock, "today", lambda zone=None: TODAY)
    session.add(Profile(id=1, birth_date=dt.date(1990, 6, 15), sex="female", height_cm=170))
    session.add(BodyMeasurement(measured_on=TODAY, kind="weight", value=65))
    session.add(BodyMeasurement(measured_on=TODAY, kind="waist", value=80))
    session.commit()
    context = _context(session)
    assert context["profile"] == {"age_years": 35, "sex": "female", "height_cm": 170, "weight_kg": 65, "weight_date": TODAY.isoformat(), "bmi": 22.5}
    text = json.dumps(context)
    assert "1990" not in text and "birth" not in text and "waist" not in text


def test_profile_only_has_the_known_fields(session, monkeypatch):
    from db.models import Profile

    session.add(Profile(id=1, sex="male"))
    session.commit()
    assert _context(session)["profile"] == {"sex": "male"}


def test_the_ai_prompt_treats_profile_as_context_and_forbids_diagnosis():
    from services.briefing_writer import PROMPT

    assert "profile" in PROMPT and "printed on the report" in PROMPT and "do not diagnose" in PROMPT


def test_profile_block_has_exactly_the_allowed_keys_including_the_weight_date(session, monkeypatch):
    from db.models import BodyMeasurement, Profile
    from services import clock

    monkeypatch.setattr(clock, "today", lambda zone=None: TODAY)
    session.add(Profile(id=1, birth_date=dt.date(1990, 6, 15), sex="female", height_cm=170))
    session.add(BodyMeasurement(measured_on=TODAY - dt.timedelta(days=3), kind="weight", value=65))
    session.add(BodyMeasurement(measured_on=TODAY - dt.timedelta(days=9), kind="waist", value=80))
    session.commit()
    profile = _context(session)["profile"]
    assert set(profile) == {"age_years", "sex", "height_cm", "weight_kg", "weight_date", "bmi"}
    assert profile["weight_date"] == (TODAY - dt.timedelta(days=3)).isoformat()


def test_the_ai_prompt_says_profile_values_carry_dates():
    from services.briefing_writer import PROMPT

    assert "weight_date" in PROMPT
