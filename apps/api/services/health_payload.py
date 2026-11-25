"""Reads wearable payloads into {date: {DailyMetric field: value}}.

Two shapes are accepted: the iOS Health Auto Export JSON ({"data": {"metrics": [...]}}) and a flat
{"date": "YYYY-MM-DD", "hrv_sdnn": 48, ...} that is easy to send from a shortcut or curl.
The Health Connect Webhook app's records go through hc_records instead: it resends records, so they are stored
by id (services/metrics_store.store_hc_records) and the day is recomputed from what is stored.
"""
import datetime as dt
from collections import defaultdict
from typing import NamedTuple

DAILY_FIELDS = ("resting_hr", "hrv_sdnn", "sleep_total_min", "sleep_deep_min", "sleep_rem_min", "steps", "vo2_max", "skin_temp_delta")
AUTO_EXPORT_QTY_FIELDS = {
    "resting_heart_rate": "resting_hr", "heart_rate_variability": "hrv_sdnn", "step_count": "steps",
    "vo2_max": "vo2_max", "apple_sleeping_wrist_temperature": "skin_temp_delta",
}
AUTO_EXPORT_SLEEP_FIELDS = {"sleep_total_min": ("totalSleep", "asleep"), "sleep_deep_min": ("deep",), "sleep_rem_min": ("rem",)}
SUMMED_FIELDS = {"steps", "sleep_total_min", "sleep_deep_min", "sleep_rem_min"}


class PayloadError(ValueError):
    """The payload is not a health-sync shape the app understands."""


class NoMetricsError(PayloadError):
    """Well-formed, but no daily metric the app knows is in it (a body-only payload, for one)."""


def _number(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PayloadError(f"{what} must be a number.")
    return float(value)


def _day(value: object) -> dt.date:
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        raise PayloadError("Each reading needs a date such as 2026-11-10.") from None


def _sleep_minutes(entry: dict, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if entry.get(key) is not None:
            return _number(entry[key], key) * 60
    return None


def _collect_auto_export(metrics: object) -> dict[dt.date, dict[str, list[float]]]:
    if not isinstance(metrics, list):
        raise PayloadError("data.metrics must be a list.")
    readings: dict[dt.date, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for metric in metrics:
        if not isinstance(metric, dict) or not isinstance(metric.get("data"), list):
            raise PayloadError("Each metric needs a name and a data list.")
        name = metric.get("name")
        for entry in metric["data"]:
            day = _day(entry.get("date"))
            if name in AUTO_EXPORT_QTY_FIELDS and entry.get("qty") is not None:
                readings[day][AUTO_EXPORT_QTY_FIELDS[name]].append(_number(entry["qty"], "qty"))
            elif name == "sleep_analysis":
                for field, keys in AUTO_EXPORT_SLEEP_FIELDS.items():
                    minutes = _sleep_minutes(entry, keys)
                    if minutes is not None:
                        readings[day][field].append(minutes)
    return readings


def _combine(values: list[float], field: str) -> float:
    return sum(values) if field in SUMMED_FIELDS else sum(values) / len(values)


def _parse_flat(payload: dict) -> dict[dt.date, dict[str, float]]:
    if "date" not in payload:
        raise PayloadError("Send a date and at least one metric.")
    fields: dict[str, float] = {f: _number(payload[f], f) for f in DAILY_FIELDS if payload.get(f) is not None}
    return {_day(payload["date"]): fields}


# Health Connect Webhook app (github.com/mcnaveen/health-connect-webhook): {"timestamp", "app_version", "steps": [...], ...}.
# Its timestamps should be "Local time" (the app's default) so the first 10 characters are the local day.
HC_AVERAGED = {
    "resting_heart_rate": ("bpm", "resting_hr"),
    "heart_rate_variability": ("rmssd_millis", "hrv_sdnn"),  # RMSSD, not SDNN; the same column the other sources fill
    "skin_temperature": ("delta_celsius", "skin_temp_delta"),
}
HC_AWAKE_STAGES = {"1", "3", "7"}  # Health Connect STAGE_TYPE_AWAKE, OUT_OF_BED, AWAKE_IN_BED


def is_hc_webhook(payload: object) -> bool:
    return isinstance(payload, dict) and "app_version" in payload and "timestamp" in payload and "date" not in payload


def _records(payload: dict, key: str) -> list[dict]:
    value = payload.get(key)
    return [e for e in value if isinstance(e, dict)] if isinstance(value, list) else []


def _sleep_stage(stage: object) -> str:
    text = str(stage).lower()
    if text in HC_AWAKE_STAGES or "awake" in text or "out_of_bed" in text:
        return "awake"
    if text == "5" or "deep" in text:
        return "sleep_deep_min"
    if text == "6" or "rem" in text:
        return "sleep_rem_min"
    return "asleep"


class HcRecord(NamedTuple):
    key: str  # "<Health Connect record id>|<field>": a resent or edited record replaces itself
    field: str
    day: dt.date
    value: float
    origin: str  # package of the app that wrote it


def _day_or_none(value: object) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _hc_base(kind: str, entry: dict, when: object) -> tuple[str, str]:
    """(record key without the field, origin). Aggregates without an id are keyed by type and time, as the app's docs say."""
    meta = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    origin = str(meta.get("data_origin") or "")
    return (str(meta["id"]) if meta.get("id") else f"{kind}@{when}@{origin}"), origin


def hc_records(payload: dict) -> list[HcRecord]:
    """Every daily-field contribution in the payload. A record with a missing number or date is skipped, not fatal:
    one odd record must not bounce a batch of thousands, which the app would then retry forever."""
    out: list[HcRecord] = []

    def add(kind: str, entry: dict, when: object, field: str, value: object) -> None:
        number, day = _finite(value), _day_or_none(when)
        if number is not None and day is not None:
            base, origin = _hc_base(kind, entry, when)
            out.append(HcRecord(f"{base}|{field}", field, day, number, origin))

    for entry in _records(payload, "steps"):
        add("steps", entry, entry.get("start_time"), "steps", entry.get("count"))
    for kind, (value_key, field) in HC_AVERAGED.items():
        for entry in _records(payload, kind):
            add(kind, entry, entry.get("time"), field, entry.get(value_key))
    for night in _records(payload, "sleep"):
        when = night.get("session_end_time")  # a night belongs to the day you wake up
        stages = _records(night, "stages")
        minutes = {"sleep_total_min": 0.0, "sleep_deep_min": 0.0, "sleep_rem_min": 0.0}
        for stage in stages:
            kind, seconds = _sleep_stage(stage.get("stage")), _finite(stage.get("duration_seconds"))
            if kind != "awake" and seconds is not None:
                minutes["sleep_total_min"] += seconds / 60
                if kind in minutes:
                    minutes[kind] += seconds / 60
        if not stages:
            seconds = _finite(night.get("duration_seconds"))
            minutes = {"sleep_total_min": seconds / 60} if seconds is not None else {}
        for field, value in minutes.items():
            add("sleep", night, when, field, value)
    return out


def hc_deleted_ids(payload: dict) -> list[str]:
    return [str(d["id"]) for d in _records(payload, "deleted") if d.get("id")]


def hc_day_totals(records: list[HcRecord]) -> dict[str, float]:
    """One day's fields from its stored records. When two apps wrote the same thing (a phone app and a watch app),
    only the app with the most of it counts, so a night or a walk is never counted twice.
    ponytail: the biggest source wins per field; use Health Connect's own app priority if that ever picks wrong."""
    by_field: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in records:
        by_field[r.field][r.origin].append(r.value)
    totals: dict[str, float] = {}
    for field, origins in by_field.items():
        if field in SUMMED_FIELDS:
            totals[field] = max(sum(v) for v in origins.values())
        else:
            values = max(origins.values(), key=len)
            totals[field] = sum(values) / len(values)
    return totals


def parse_payload(payload: object) -> dict[dt.date, dict[str, float]]:
    if not isinstance(payload, dict):
        raise PayloadError("The body must be a JSON object.")
    if isinstance(payload.get("data"), dict) and "metrics" in payload["data"]:
        readings = _collect_auto_export(payload["data"]["metrics"])
        days = {day: {f: _combine(v, f) for f, v in fields.items()} for day, fields in readings.items()}
    else:
        days = _parse_flat(payload)
    days = {day: fields for day, fields in days.items() if fields}
    if not days:
        raise NoMetricsError("No known metric found. Send at least one of: " + ", ".join(DAILY_FIELDS) + ".")
    return days


# --- body data (weight, fat, waist ...) -> BodyMeasurement kinds, never DailyMetric ---
import math  # noqa: E402

LB_TO_KG = 0.45359237
IN_TO_CM = 2.54
BODY_FLAT_KEYS = {
    "weight_kg": ("weight", 1.0), "weight_lb": ("weight", LB_TO_KG), "weight_lbs": ("weight", LB_TO_KG),
    "body_fat_pct": ("body_fat_pct", 1.0), "muscle_kg": ("muscle_kg", 1.0), "body_water_pct": ("body_water_pct", 1.0),
    "bone_kg": ("bone_kg", 1.0), "visceral_fat": ("visceral_fat", 1.0), "bmr_kcal": ("bmr_kcal", 1.0),
    "skeletal_muscle_kg": ("skeletal_muscle_kg", 1.0), "skeletal_muscle_pct": ("skeletal_muscle_pct", 1.0),
    "protein_pct": ("protein_pct", 1.0), "body_age": ("body_age", 1.0),
    "hip": ("hip", 1.0), "fat_mass_kg": ("fat_mass_kg", 1.0), "lean_mass_kg": ("lean_mass_kg", 1.0), "active_cell_mass_kg": ("active_cell_mass_kg", 1.0), "active_cell_mass_pct": ("active_cell_mass_pct", 1.0), "total_body_water_kg": ("total_body_water_kg", 1.0), "extracellular_water_kg": ("extracellular_water_kg", 1.0), "ecw_icw_ratio": ("ecw_icw_ratio", 1.0), "phase_angle": ("phase_angle", 1.0), "specific_bmr": ("specific_bmr", 1.0),
    "waist_cm": ("waist", 1.0), "waist_in": ("waist", IN_TO_CM),
}


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _auto_export_body_value(name: str, units: str, qty: float) -> tuple[str, float] | None:
    unit = units.strip().lower().replace(" ", "")
    if name == "weight_body_mass":
        if unit in ("", "kg"):
            return "weight", qty
        if unit in ("lb", "lbs"):
            return "weight", qty * LB_TO_KG
    elif name == "body_fat_percentage":
        # Health Auto Export sends percent numbers such as 18.5. Only a value of 1.0 or less with an empty or "%" unit
        # is read as a 0-1 fraction (real body fat is never below 2 %), so 0.185 becomes 18.5.
        if unit in ("", "%"):
            return "body_fat_pct", qty * 100 if 0 < qty <= 1.0 else qty
    elif name == "waist_circumference":
        if unit in ("", "cm"):
            return "waist", qty
        if unit in ("in", "inch", "inches"):
            return "waist", qty * IN_TO_CM
    return None  # lean_body_mass and everything else is ignored


def _valid_body(kind: str, value: float) -> float | None:
    from services.profile import in_range

    value = round(value, 2)
    return value if in_range(kind, value) else None


def parse_body(payload: object) -> dict[dt.date, dict[str, float]]:
    """Body readings from either shape; unknown, non-numeric, non-finite, out-of-range values and bad dates are dropped."""
    found: dict[dt.date, dict[str, tuple[str, float]]] = defaultdict(dict)  # day -> kind -> (entry date text, value)
    if not isinstance(payload, dict):
        return {}

    def keep(day_text: object, kind: str, value: float) -> None:
        checked = _valid_body(kind, value)
        try:
            day = dt.date.fromisoformat(str(day_text)[:10])
        except ValueError:
            return
        if checked is not None and (kind not in found[day] or str(day_text) >= found[day][kind][0]):
            found[day][kind] = (str(day_text), checked)

    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("metrics"), list):
        for metric in data["metrics"]:
            if not isinstance(metric, dict) or not isinstance(metric.get("data"), list):
                continue
            units = metric.get("units") if isinstance(metric.get("units"), str) else ""
            for entry in metric["data"]:
                qty = _finite(entry.get("qty")) if isinstance(entry, dict) else None
                converted = _auto_export_body_value(str(metric.get("name")), units, qty) if qty is not None else None
                if converted:
                    keep(entry.get("date"), *converted)
    elif is_hc_webhook(payload):
        for key, value_key, kind in (("weight", "kilograms", "weight"), ("body_fat", "percentage", "body_fat_pct")):
            for entry in _records(payload, key):
                number = _finite(entry.get(value_key))
                if number is not None:
                    keep(entry.get("time"), kind, number)
    elif "date" in payload:
        for key, (kind, factor) in BODY_FLAT_KEYS.items():
            number = _finite(payload.get(key))
            if number is not None:
                keep(payload["date"], kind, number * factor)
    return {day: {kind: v for kind, (_, v) in kinds.items()} for day, kinds in found.items() if kinds}
