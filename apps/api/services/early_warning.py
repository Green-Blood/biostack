"""Early-warning risk score, 0 to 100, from the last 48 hours of logged data.

Six factors, each worth at most its weight (the weights add up to 100). A factor is worth the full weight at
its "severe" level, nothing at or beyond its "calm" level, and a proportional share in between:

  pressure_drop     20  24 h pressure change, severe at -8 mmHg or lower, calm at 0 or above
  late_caffeine     15  caffeine still in the body at the latest bedtime, severe at 100 mg or more
  deep_sleep_drop   20  last night's deep sleep below your own 28-day average, severe at 40 % below
  hrv_drop          20  HRV below your own 28-day average, severe at 25 % below
  air_quality       10  mean PM2.5 over 48 h, calm at 15 ug/m3 (WHO daily guideline), severe at 50 ug/m3 or more
  cns_drop          15  latest tap test below your 14-day tap baseline, severe at 20 % below

score = round(100 * sum(points of factors that have data) / sum(weights of factors that have data)).
A factor without data (nothing logged in the last 48 h, or under 7 days of history for a personal average) is
left out of both sums, so missing data never lowers the score. With fewer than two factors that have data the
score is None and `reason` says what to log; no number is invented. The alert fires above 70. Level: low below
30, moderate up to 70, high above. Cached correlations never change the score; they mark which factors your own
data has linked to a drop, and are quoted in the recommendations.
"""
import datetime as dt
from dataclasses import dataclass, field, replace

from sqlmodel import Session, select

from db.models import CnsTest, CorrelationCache, DailyMetric, EnvironmentalLog, SupplementLog
from services.correlation_phrases import describe
from services.correlation_store import load_correlations
from services.half_life_engine import DEFAULT_HALF_LIFE_HOURS, Dose, as_utc, bedtime_moment, remaining_at
from services.i18n import msg

WINDOW = dt.timedelta(hours=48)
BASELINE_DAYS = 28
MIN_BASELINE_DAYS = 7
ALERT_ABOVE = 70
MIN_FACTORS_WITH_DATA = 2
NOTHING_LOGGED = "Nothing logged in the last 48 hours."

FACTOR_WEIGHTS = {
    "pressure_drop": 20, "late_caffeine": 15, "deep_sleep_drop": 20, "hrv_drop": 20, "air_quality": 10, "cns_drop": 15,
}
CORRELATION_KEYS = {
    "late_caffeine": "caffeine_at_bedtime", "air_quality": "pm2_5", "pressure_drop": "pressure_delta_24h",
}


@dataclass(frozen=True)
class Factor:
    key: str
    label: str
    weight: int
    points: float = 0.0
    detail: str = NOTHING_LOGGED
    has_data: bool = False
    seen_in_days: int | None = None


@dataclass
class RiskAssessment:
    score: int | None
    level: str | None
    alert: bool
    reason: str
    factors: list[Factor] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


def _share(amount: float, severe_at: float) -> float:
    """0 at no change, 1 at the severe level, clamped."""
    return min(max(amount / severe_at, 0.0), 1.0)


def _factor(key: str, share: float, detail: str, lang: str) -> Factor:
    weight = FACTOR_WEIGHTS[key]
    return Factor(key, msg(lang, f"ew.label.{key}"), weight, round(weight * share, 1), detail, has_data=True)


def _no_data(key: str, lang: str, detail: str | None = None) -> Factor:
    return Factor(key, msg(lang, f"ew.label.{key}"), FACTOR_WEIGHTS[key], detail=detail or msg(lang, "ew.nothing_logged"))


def _pressure(readings: list[EnvironmentalLog], lang: str) -> Factor:
    deltas = [r for r in readings if r.pressure_delta_24h is not None]
    if not deltas:
        return _no_data("pressure_drop", lang)
    delta = max(deltas, key=lambda r: as_utc(r.timestamp)).pressure_delta_24h
    return _factor("pressure_drop", _share(-delta, 8), msg(lang, "ew.pressure", delta=f"{delta:+.1f}"), lang)


def _air(readings: list[EnvironmentalLog], lang: str) -> Factor:
    values = [r.pm2_5 for r in readings if r.pm2_5 is not None]
    if not values:
        return _no_data("air_quality", lang)
    mean = sum(values) / len(values)
    return _factor("air_quality", _share(mean - 15, 35), msg(lang, "ew.air", mean=f"{mean:.0f}"), lang)


def caffeine_remaining(session: Session, moment: dt.datetime) -> float:
    """Milligrams of logged caffeine still in the body at the given moment."""
    logs = session.exec(select(SupplementLog).where(SupplementLog.timestamp <= moment)).all()
    doses = [Dose(log.timestamp, log.dosage or 0.0, log.half_life_hours) for log in logs if log.item_name.strip().lower() == "caffeine"]
    return remaining_at(doses, moment, DEFAULT_HALF_LIFE_HOURS["caffeine"])


def _caffeine(session: Session, now: dt.datetime, bedtime: str, zone: dt.tzinfo, lang: str) -> Factor:
    week_ago = now - dt.timedelta(days=7)
    if session.exec(select(SupplementLog).where(SupplementLog.timestamp >= week_ago)).first() is None:
        return _no_data("late_caffeine", lang, msg(lang, "ew.no_supplements"))
    today = now.astimezone(zone).date()
    last_bedtime = bedtime_moment(today, bedtime, zone)
    if last_bedtime > now:
        last_bedtime = bedtime_moment(today - dt.timedelta(days=1), bedtime, zone)
    remaining = caffeine_remaining(session, last_bedtime)
    return _factor("late_caffeine", _share(remaining, 100), msg(lang, "ew.caffeine", mg=f"{remaining:.0f}"), lang)


def _below_average(session: Session, key: str, attribute: str, severe_drop: float, today: dt.date, lang: str) -> Factor:
    metrics = session.exec(select(DailyMetric).where(DailyMetric.metric_date >= today - dt.timedelta(days=BASELINE_DAYS))).all()
    recent = [m for m in metrics if m.metric_date >= today - dt.timedelta(days=1) and getattr(m, attribute) is not None]
    history = [getattr(m, attribute) for m in metrics if m.metric_date < today - dt.timedelta(days=1) and getattr(m, attribute) is not None]
    if not recent:
        return _no_data(key, lang)
    if len(history) < MIN_BASELINE_DAYS:
        return _no_data(key, lang, msg(lang, "ew.needs_baseline", min=MIN_BASELINE_DAYS, have=len(history)))
    latest = getattr(max(recent, key=lambda m: m.metric_date), attribute)
    average = sum(history) / len(history)
    drop = (average - latest) / average
    return _factor(key, _share(drop, severe_drop), msg(lang, "ew.below_average", latest=f"{latest:.0f}", average=f"{average:.0f}"), lang)


def _tap_speed(session: Session, now: dt.datetime, lang: str) -> Factor:
    tests = [t for t in session.exec(select(CnsTest).where(CnsTest.timestamp >= now - WINDOW)) if t.baseline_dev_pct is not None]
    if not tests:
        return _no_data("cns_drop", lang)
    deviation = max(tests, key=lambda t: as_utc(t.timestamp)).baseline_dev_pct
    return _factor("cns_drop", _share(-deviation, 20), msg(lang, "ew.tap", dev=f"{deviation:+.0f}"), lang)


def _mark_seen(factors: list[Factor], correlations: list[CorrelationCache]) -> list[Factor]:
    days = {c.trigger_key: c.n_days for c in correlations}
    return [replace(f, seen_in_days=days.get(CORRELATION_KEYS.get(f.key, ""))) for f in factors]


def _recommendations(factors: list[Factor], correlations: list[CorrelationCache], lang: str) -> list[str]:
    by_trigger = {c.trigger_key: c for c in correlations}
    advice = []
    for factor in sorted((f for f in factors if f.points > 0), key=lambda f: f.points, reverse=True):
        text = msg(lang, f"ew.advice.{factor.key}")
        link = by_trigger.get(CORRELATION_KEYS.get(factor.key, ""))
        if link:
            phrase, _ = describe(link.trigger_key, link.target_metric, link.correlation_score, link.lag_hours, lang)
            text += " " + msg(lang, "ew.link", phrase=phrase, n_days=link.n_days)
        advice.append(text)
    return advice


def assess_risk(session: Session, now: dt.datetime, bedtime: str, zone: dt.tzinfo, lang: str = "en") -> RiskAssessment:
    now = as_utc(now)
    today = now.astimezone(zone).date()
    readings = session.exec(select(EnvironmentalLog).where(EnvironmentalLog.timestamp >= now - WINDOW)).all()
    correlations = load_correlations(session)
    factors = _mark_seen([
        _pressure(readings, lang), _caffeine(session, now, bedtime, zone, lang),
        _below_average(session, "deep_sleep_drop", "sleep_deep_min", 0.4, today, lang),
        _below_average(session, "hrv_drop", "hrv_sdnn", 0.25, today, lang),
        _air(readings, lang), _tap_speed(session, now, lang),
    ], correlations)
    with_data = [f for f in factors if f.has_data]
    if len(with_data) < MIN_FACTORS_WITH_DATA:
        reason = msg(lang, "ew.reason", n=len(with_data), total=len(factors), min=MIN_FACTORS_WITH_DATA)
        return RiskAssessment(None, None, False, reason, factors)
    score = round(100 * sum(f.points for f in with_data) / sum(f.weight for f in with_data))
    alert = score > ALERT_ABOVE
    level = "high" if alert else "moderate" if score >= 30 else "low"
    return RiskAssessment(score, level, alert, "", factors, _recommendations(factors, correlations, lang) if alert else [])
