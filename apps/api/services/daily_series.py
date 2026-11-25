"""Turns logged rows into the per-day series the lag analyzer works on (dates are the owner's local days).

Targets: HRV, deep sleep (from DailyMetric) and the day's worst symptom severity (no symptom logged between the
first and last journal entry counts as 0). Predictors: caffeine left in the body at bedtime, daily mean PM2.5 and
24-hour pressure change, and one 0/1 flag per supplement (protector) or other stimulant (trigger) over the period
in which any supplement was logged. Medications are left out because why they were taken confounds the result.
"""
import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from sqlmodel import Session, select

from db.models import DailyMetric, EnvironmentalLog, HealthJournal, SupplementLog
from services.half_life_engine import DEFAULT_HALF_LIFE_HOURS, FALLBACK_HALF_LIFE_HOURS, Dose, as_utc, at_bedtime
from services.i18n import msg
from services.lag_analyzer import DailySeries

CAFFEINE = "caffeine"


@dataclass(frozen=True)
class Variable:
    key: str
    label: str
    kind: str  # "symptom" | "trigger" | "protector"


TARGETS = {
    "hrv_sdnn": Variable("hrv_sdnn", "HRV (SDNN)", "symptom"),
    "sleep_deep_min": Variable("sleep_deep_min", "Deep sleep", "symptom"),
    "symptom_severity": Variable("symptom_severity", "Worst symptom of the day", "symptom"),
}
_FIXED_PREDICTORS = {
    "caffeine_at_bedtime": Variable("caffeine_at_bedtime", "Caffeine left at bedtime", "trigger"),
    "pm2_5": Variable("pm2_5", "PM2.5 air pollution", "trigger"),
    "pressure_delta_24h": Variable("pressure_delta_24h", "Air pressure change over 24 h", "trigger"),
}


def variable_for(key: str, lang: str = "en") -> Variable:
    """The Variable behind any target or predictor key, including the per-supplement flags."""
    known = {**TARGETS, **_FIXED_PREDICTORS}.get(key)
    if known:
        return Variable(key, msg(lang, f"var.{key}"), known.kind)
    kind, _, name = key.partition(":")
    return Variable(key, msg(lang, "var.taken", name=name.capitalize()), kind)


def label_for(key: str) -> str:
    return variable_for(key).label


def _date_range(first: dt.date, last: dt.date) -> list[dt.date]:
    return [first + dt.timedelta(days=i) for i in range((last - first).days + 1)]


def _local_day(moment: dt.datetime, zone: dt.tzinfo) -> dt.date:
    return as_utc(moment).astimezone(zone).date()


def build_targets(session: Session) -> dict[str, DailySeries]:
    metrics = session.exec(select(DailyMetric)).all()
    targets = {
        key: {m.metric_date: float(getattr(m, key)) for m in metrics if getattr(m, key) is not None}
        for key in ("hrv_sdnn", "sleep_deep_min")
    }
    entries = session.exec(select(HealthJournal)).all()
    if entries:
        worst: dict[dt.date, float] = defaultdict(float)
        for entry in entries:
            if entry.category == "symptom" and entry.severity_1_10 is not None:
                worst[entry.entry_date] = max(worst[entry.entry_date], float(entry.severity_1_10))
        days = _date_range(min(e.entry_date for e in entries), max(e.entry_date for e in entries))
        targets["symptom_severity"] = {day: worst.get(day, 0.0) for day in days}
    return {key: series for key, series in targets.items() if series}


def _caffeine_series(logs: list[SupplementLog], days: list[dt.date], bedtime: str, zone: dt.tzinfo) -> DailySeries:
    doses = [Dose(log.timestamp, log.dosage or 0.0, log.half_life_hours) for log in logs]
    default = DEFAULT_HALF_LIFE_HOURS.get(CAFFEINE, FALLBACK_HALF_LIFE_HOURS)
    return {day: at_bedtime(doses, day, bedtime, zone, default) for day in days}


def _flag_series(logs: list[SupplementLog], days: list[dt.date], zone: dt.tzinfo) -> DailySeries:
    taken = {_local_day(log.timestamp, zone) for log in logs}
    return {day: 1.0 if day in taken else 0.0 for day in days}


def _supplement_predictors(
    session: Session, bedtime: str, zone: dt.tzinfo,
) -> tuple[dict[str, DailySeries], dict[str, Variable]]:
    logs = session.exec(select(SupplementLog).where(SupplementLog.category != "medication")).all()
    if not logs:
        return {}, {}
    days = _date_range(*(f(_local_day(log.timestamp, zone) for log in logs) for f in (min, max)))
    by_name: dict[str, list[SupplementLog]] = defaultdict(list)
    for log in logs:
        by_name[log.item_name.strip().lower()].append(log)
    series: dict[str, DailySeries] = {}
    variables: dict[str, Variable] = {}
    for name, named_logs in by_name.items():
        if name == CAFFEINE:
            series["caffeine_at_bedtime"] = _caffeine_series(named_logs, days, bedtime, zone)
            variables["caffeine_at_bedtime"] = _FIXED_PREDICTORS["caffeine_at_bedtime"]
            continue
        stimulant = any(log.category == "stimulant" for log in named_logs)
        key = f"{'trigger' if stimulant else 'protector'}:{name}"
        series[key] = _flag_series(named_logs, days, zone)
        label = named_logs[0].item_name.strip()
        variables[key] = Variable(key, f"{label} taken", "trigger" if stimulant else "protector")
    return series, variables


def _environment_predictors(session: Session, zone: dt.tzinfo) -> tuple[dict[str, DailySeries], dict[str, Variable]]:
    readings: dict[str, dict[dt.date, list[float]]] = {"pm2_5": defaultdict(list), "pressure_delta_24h": defaultdict(list)}
    for log in session.exec(select(EnvironmentalLog)):
        for key, per_day in readings.items():
            if getattr(log, key) is not None:
                per_day[_local_day(log.timestamp, zone)].append(float(getattr(log, key)))
    series = {key: {day: sum(v) / len(v) for day, v in per_day.items()} for key, per_day in readings.items() if per_day}
    return series, {key: _FIXED_PREDICTORS[key] for key in series}


def build_predictors(session: Session, bedtime: str, zone: dt.tzinfo) -> tuple[dict[str, DailySeries], dict[str, Variable]]:
    supplement_series, supplement_variables = _supplement_predictors(session, bedtime, zone)
    environment_series, environment_variables = _environment_predictors(session, zone)
    return {**supplement_series, **environment_series}, {**supplement_variables, **environment_variables}
