"""Everything logged in the last 72 hours as one compact JSON-ready dict, for the daily briefing.

Only what the owner is told is sent: names and values, never documents. Journal entries contribute a date and a
severity for symptoms only; their titles, descriptions and body locations stay local.
"""
import datetime as dt

from sqlmodel import Session, select

from db.models import (
    Biomarker, CnsTest, CorrelationCache, DailyMetric, EnvironmentalLog, HealthJournal, LabReport, Medication, SupplementLog,
)
from services import clock
from services.correlation_phrases import describe
from services.correlation_store import load_correlations
from services.early_warning import assess_risk, caffeine_remaining
from services.half_life_engine import as_utc, bedtime_moment
from services.courses import course_status, marker_name
from services.freshness import interval_for, load_overrides
from services.markers import marker_display_name
from services.profile import profile_payload

WINDOW_HOURS = 72
TOP_CORRELATIONS = 5
MAX_BIOMARKERS = 10
RECENT_COURSE_DAYS = 14  # a course counts as just finished for this long


def _iso(moment: dt.datetime) -> str:
    return as_utc(moment).isoformat()


def _upcoming_bedtime(now: dt.datetime, bedtime: str, zone: dt.tzinfo) -> dt.datetime:
    today = now.astimezone(zone).date()
    tonight = bedtime_moment(today, bedtime, zone)
    return tonight if tonight >= now else bedtime_moment(today + dt.timedelta(days=1), bedtime, zone)


def latest_out_of_range(session: Session, lang: str = "en", today: dt.date | None = None) -> list[dict]:
    today = today or clock.today()
    overrides = load_overrides(session)
    dates = {report.id: report.test_date for report in session.exec(select(LabReport))}
    latest: dict[str, Biomarker] = {}
    for marker in session.exec(select(Biomarker).where(Biomarker.value.is_not(None))):
        known = latest.get(marker.marker_key)
        if known is None or dates[marker.report_id] > dates[known.report_id]:
            latest[marker.marker_key] = marker
    flagged = sorted((m for m in latest.values() if m.is_out_of_range), key=lambda m: dates[m.report_id], reverse=True)
    out = []
    for m in flagged[:MAX_BIOMARKERS]:
        age = max((today - dates[m.report_id]).days, 0)
        retest, _ = interval_for(m.marker_key, overrides)
        out.append({"marker_key": m.marker_key, "name": marker_display_name(m.marker_key, m.display_name, lang), "value": m.value, "unit": m.unit, "ref_min": m.ref_min,
                    "ref_max": m.ref_max, "test_date": dates[m.report_id].isoformat(), "age_days": age,
                    "stale": retest is not None and age > retest})
    return out


def data_age(out_of_range: list[dict]) -> list[dict]:
    """How old each out-of-range result is and whether it is past its re-test interval (names and numbers only)."""
    return [{"marker_key": m["marker_key"], "name": m["name"], "age_days": m["age_days"], "stale": m["stale"]} for m in out_of_range]


def recent_courses(session: Session, today: dt.date, lang: str) -> list[dict]:
    """Running and just-finished courses: name and dates only, plus the marker they target."""
    out = []
    for c in session.exec(select(Medication).order_by(Medication.start_date.desc())):
        status = course_status(c, today)
        if status in ("planned", "undated") or (status == "finished" and (today - c.end_date).days > RECENT_COURSE_DAYS):
            continue
        out.append({"id": c.id, "name": c.name, "status": status, "start": c.start_date.isoformat() if c.start_date else None,
                    "end": c.end_date.isoformat() if c.end_date else None, "target_marker_key": c.target_marker_key, "target_marker": marker_name(session, c.target_marker_key, lang)})
    return out


def _correlation(c: CorrelationCache, lang: str) -> dict:
    phrase, effect = describe(c.trigger_key, c.target_metric, c.correlation_score, c.lag_hours, lang)
    return {"target": c.target_metric, "trigger": c.trigger_key, "lag_hours": c.lag_hours, "phrase": phrase,
            "effect": effect, "p": round(c.p_value, 4), "n_days": c.n_days}


def profile_context(session: Session) -> dict:
    """Age in years (never the birth date), sex, height, latest weight with its date, and BMI: only the known ones."""
    p = profile_payload(session)
    known = {"age_years": p["age_years"], "sex": p["sex"], "height_cm": p["height_cm"],
             "weight_kg": p["latest_weight"]["kg"] if p["latest_weight"] else None,
             "weight_date": p["latest_weight"]["date"] if p["latest_weight"] else None, "bmi": p["bmi"]["value"] if p["bmi"] else None}
    return {k: v for k, v in known.items() if v is not None}


def build_context(session: Session, now: dt.datetime, bedtime: str, zone: dt.tzinfo, lang: str = "en") -> dict:
    now = as_utc(now)
    since = now - dt.timedelta(hours=WINDOW_HOURS)
    since_day = since.astimezone(zone).date()
    risk = assess_risk(session, now, bedtime, zone, lang)
    today = now.astimezone(zone).date()
    out_of_range = latest_out_of_range(session, lang, today)
    profile = profile_context(session)
    return {
        **({"profile": profile} if profile else {}),
        "generated_at": _iso(now),
        "window_hours": WINDOW_HOURS,
        "daily_metrics": [
            {"date": m.metric_date.isoformat(), **m.model_dump(mode="json", exclude={"source", "metric_date"})}
            for m in session.exec(select(DailyMetric).where(DailyMetric.metric_date >= since_day).order_by(DailyMetric.metric_date))
        ],
        "supplements": [
            {"time": _iso(s.timestamp), "item": s.item_name, "dosage": s.dosage, "unit": s.unit, "category": s.category}
            for s in session.exec(select(SupplementLog).where(SupplementLog.timestamp >= since).order_by(SupplementLog.timestamp))
        ],
        "symptoms": [
            {"date": e.entry_date.isoformat(), "severity": e.severity_1_10}
            for e in session.exec(select(HealthJournal).where(
                HealthJournal.entry_date >= since_day, HealthJournal.category == "symptom").order_by(HealthJournal.entry_date))
        ],
        "cns_tests": [
            {"time": _iso(t.timestamp), "taps": t.tap_count_10s, "baseline_dev_pct": t.baseline_dev_pct}
            for t in session.exec(select(CnsTest).where(CnsTest.timestamp >= since).order_by(CnsTest.timestamp))
        ],
        "environment": [
            {"time": _iso(e.timestamp), "pm2_5": e.pm2_5, "aqi": e.aqi, "pressure_mmHg": e.pressure_mmHg,
             "pressure_delta_24h": e.pressure_delta_24h}
            for e in session.exec(select(EnvironmentalLog).where(EnvironmentalLog.timestamp >= since).order_by(EnvironmentalLog.timestamp))
        ],
        "caffeine_left_at_tonights_bedtime_mg": round(caffeine_remaining(session, _upcoming_bedtime(now, bedtime, zone)), 1),
        "risk": {
            "score": risk.score, "level": risk.level, "reason": risk.reason, "recommendations": risk.recommendations,
            "factors": [{"label": f.label, "points": f.points, "weight": f.weight, "detail": f.detail} for f in risk.factors if f.has_data],
        },
        "correlations": [_correlation(c, lang) for c in load_correlations(session)[:TOP_CORRELATIONS]],
        "out_of_range_biomarkers": out_of_range,
        "data_age": data_age(out_of_range),
        "courses": recent_courses(session, today, lang),
    }
