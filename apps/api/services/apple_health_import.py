"""Streaming importer for Apple Health export ZIP archives (apple_health_export/export.xml)."""
from collections import defaultdict
import datetime as dt
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from sqlmodel import Session

from services import wearable_ingest

SOURCE = "apple_health"

_SUM_TYPES = {
    "HKQuantityTypeIdentifierStepCount": "steps",
    "HKQuantityTypeIdentifierDistanceWalkingRunning": "distance_m",
    "HKQuantityTypeIdentifierActiveEnergyBurned": "active_kcal",
}
_MEAN_TYPES = {
    "HKQuantityTypeIdentifierRestingHeartRate": "resting_hr",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv_sdnn",
    "HKQuantityTypeIdentifierOxygenSaturation": "spo2_avg",
}
_SLEEP_TYPE = "HKCategoryTypeIdentifierSleepAnalysis"
_SLEEP_STAGE_MAP = {
    "HKCategoryValueSleepAnalysisAsleepCore": "sleep_light_min",
    "HKCategoryValueSleepAnalysisAsleepLight": "sleep_light_min",
    "HKCategoryValueSleepAnalysisAsleepDeep": "sleep_deep_min",
    "HKCategoryValueSleepAnalysisAsleepREM": "sleep_rem_min",
    "HKCategoryValueSleepAnalysisAwake": "sleep_awake_min",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "sleep_total_min",
    "HKCategoryValueSleepAnalysisAsleep": "sleep_total_min",
}


def _find_export_xml(zf: zipfile.ZipFile) -> str | None:
    candidates = [
        name for name in zf.namelist()
        if not name.startswith("__MACOSX/") and name.lower().endswith("export.xml")
    ]
    if not candidates:
        return None
    # Prefer top-level or apple_health_export/export.xml over any nested file.
    candidates.sort(key=lambda n: (n.count("/"), len(n)))
    return candidates[0]


def looks_like_apple_health_zip(path: Path) -> bool:
    if not zipfile.is_zipfile(path):
        return False
    try:
        with zipfile.ZipFile(path) as zf:
            return _find_export_xml(zf) is not None
    except zipfile.BadZipFile:
        return False


def _parse_local_dt(raw: str | None) -> dt.datetime | None:
    if not raw or len(raw) < 19:
        return None
    try:
        return dt.datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _distance_meters(val: float, unit: str) -> float:
    u = unit.strip().lower()
    if u == "km":
        return val * 1000.0
    if u == "mi":
        return val * 1609.344
    return val


def import_apple_health_zip(session: Session, zip_path: Path) -> dict:
    """Stream export.xml from `zip_path`, aggregate daily signals, and write via wearable_ingest."""
    sums: dict[dt.date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    means: dict[dt.date, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    sleep_mins: dict[dt.date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    records_scanned = 0

    with zipfile.ZipFile(zip_path) as zf:
        entry = _find_export_xml(zf)
        if entry is None:
            raise ValueError("Missing export.xml")
        with zf.open(entry) as xml_stream:
            for _, elem in ET.iterparse(xml_stream, events=("end",)):
                if elem.tag != "Record":
                    if elem.tag != "HealthData":
                        elem.clear()
                    continue
                records_scanned += 1
                rtype = elem.attrib.get("type", "")
                if rtype in _SUM_TYPES:
                    start = _parse_local_dt(elem.attrib.get("startDate"))
                    raw_val = elem.attrib.get("value")
                    if start and raw_val is not None:
                        try:
                            val = float(raw_val)
                        except ValueError:
                            val = None
                        if val is not None and val >= 0:
                            field = _SUM_TYPES[rtype]
                            if field == "distance_m":
                                val = _distance_meters(val, elem.attrib.get("unit", "m"))
                            sums[start.date()][field] += val
                elif rtype in _MEAN_TYPES:
                    start = _parse_local_dt(elem.attrib.get("startDate"))
                    raw_val = elem.attrib.get("value")
                    if start and raw_val is not None:
                        try:
                            val = float(raw_val)
                        except ValueError:
                            val = None
                        if val is not None and val >= 0:
                            field = _MEAN_TYPES[rtype]
                            if field == "spo2_avg" and val <= 1.0:
                                val *= 100.0
                            means[start.date()][field].append(val)
                elif rtype == _SLEEP_TYPE:
                    start = _parse_local_dt(elem.attrib.get("startDate"))
                    end = _parse_local_dt(elem.attrib.get("endDate"))
                    stage = _SLEEP_STAGE_MAP.get(elem.attrib.get("value", ""))
                    if start and end and end > start and stage:
                        minutes = (end - start).total_seconds() / 60.0
                        if 0 < minutes <= 24 * 60:
                            sleep_mins[end.date()][stage] += minutes
                elem.clear()

    days: dict[dt.date, dict[str, float]] = {}
    all_dates = set(sums) | set(means) | set(sleep_mins)
    sleep_nights = 0

    for day in sorted(all_dates):
        fields: dict[str, float] = {}
        for k, total in sums.get(day, {}).items():
            fields[k] = round(total, 1) if k != "steps" else round(total)
        for k, vals in means.get(day, {}).items():
            if vals:
                fields[k] = round(sum(vals) / len(vals), 1)
        sl = sleep_mins.get(day, {})
        if sl:
            stage_total = sl.get("sleep_light_min", 0.0) + sl.get("sleep_deep_min", 0.0) + sl.get("sleep_rem_min", 0.0)
            total_min = stage_total if stage_total > 0 else sl.get("sleep_total_min", 0.0)
            if total_min > 0:
                sleep_nights += 1
                fields["sleep_total_min"] = round(total_min, 1)
                for stage_key in ("sleep_light_min", "sleep_deep_min", "sleep_rem_min", "sleep_awake_min"):
                    if sl.get(stage_key, 0.0) > 0:
                        fields[stage_key] = round(sl[stage_key], 1)
                awake = sl.get("sleep_awake_min", 0.0)
                if total_min + awake > 0:
                    fields["sleep_efficiency"] = round(total_min / (total_min + awake) * 100.0, 1)
        if fields:
            days[day] = fields

    fields_written = wearable_ingest.ingest_daily(session, days, source=SOURCE)
    return {
        "days_written": len(days),
        "fields_written": fields_written,
        "records_scanned": records_scanned,
        "sleep_nights": sleep_nights,
    }
