"""Synthetic demo data with known effects planted in it, so the analytics have something real to find.

Every row is tagged source="demo" and the generator is seeded, so results are reproducible. Three effects are
planted (the rest is noise the analyzer must ignore):

  caffeine left at bedtime  lowers   next-day HRV           (+24 h, negative)
  falling air pressure      worsens  the same day's symptom (  0 h, negative: lower delta, higher severity)
  magnesium taken           raises   next-day deep sleep     (+24 h, positive)

Removing demo data deletes the demo rows and the analytics caches built from them.
"""
import datetime as dt
import random
from dataclasses import dataclass

from sqlalchemy import delete, func, update
from sqlmodel import Session, select

from db.models import (
    DEMO_SOURCE, AppSetting, Biomarker, BriefingCache, CnsTest, CorrelationCache, DailyMetric, EnvironmentalLog, HealthJournal,
    Diagnosis, LabReport, MedicalRecord, Medication, RecordAttachment, RecordMedication, RecordNote, RecordOrgan,
    ScanMeasurement, SupplementLog,
)
from services import app_settings
from services.cns_baseline import baseline_deviation
from services.correlation_store import REPORT_KEY
from services.half_life_engine import DEFAULT_HALF_LIFE_HOURS, Dose, at_bedtime
from services.lab_rows import is_out_of_range, marker_identity

DEMO = DEMO_SOURCE
DAYS = 60
SEED = 42
BEDTIME = "23:00"
DEMO_TABLES = (SupplementLog, DailyMetric, HealthJournal, CnsTest, EnvironmentalLog, Biomarker, LabReport,
               MedicalRecord, Medication)
RECORD_CHILDREN = (ScanMeasurement, RecordOrgan, RecordMedication, Diagnosis, RecordNote, RecordAttachment)
DERIVED_TABLES = (CorrelationCache,)


@dataclass(frozen=True)
class PlantedEffect:
    lag_hours: int
    sign: int


PLANTED_LAGS = {
    ("caffeine_at_bedtime", "hrv_sdnn"): PlantedEffect(24, -1),
    ("pressure_delta_24h", "symptom_severity"): PlantedEffect(0, -1),
    ("protector:magnesium", "sleep_deep_min"): PlantedEffect(24, +1),
}


def _at(day: dt.date, hour: float, zone: dt.tzinfo) -> dt.datetime:
    clock = dt.time(int(hour), int(hour % 1 * 60))
    return dt.datetime.combine(day, clock, tzinfo=zone).astimezone(dt.timezone.utc)


def _caffeine_doses(rng: random.Random, day: dt.date, zone: dt.tzinfo) -> list[SupplementLog]:
    doses = [SupplementLog(timestamp=_at(day, 8, zone), item_name="Caffeine", dosage=200, unit="mg", category="stimulant", source=DEMO)]
    if rng.random() < 0.4:
        late = _at(day, rng.uniform(19, 21.5), zone)
        doses.append(SupplementLog(timestamp=late, item_name="Caffeine", dosage=rng.choice([100, 150, 200]), unit="mg",
                                   category="stimulant", source=DEMO))
    return doses


def _daily_logs(rng: random.Random, days: list[dt.date], zone: dt.tzinfo) -> tuple[list[SupplementLog], dict[dt.date, float], set[dt.date]]:
    logs: list[SupplementLog] = []
    caffeine_at_bedtime: dict[dt.date, float] = {}
    magnesium_days: set[dt.date] = set()
    for day in days:
        todays = _caffeine_doses(rng, day, zone)
        logs += todays
        doses = [Dose(log.timestamp, log.dosage, None) for log in todays]
        caffeine_at_bedtime[day] = at_bedtime(doses, day, BEDTIME, zone, DEFAULT_HALF_LIFE_HOURS["caffeine"])
        if rng.random() < 0.5:
            magnesium_days.add(day)
            logs.append(SupplementLog(timestamp=_at(day, 21, zone), item_name="Magnesium", dosage=400, unit="mg", source=DEMO))
        if rng.random() < 0.3:
            logs.append(SupplementLog(timestamp=_at(day, 13, zone), item_name="L-theanine", dosage=200, unit="mg", source=DEMO))
    return logs, caffeine_at_bedtime, magnesium_days


def _environment(rng: random.Random, days: list[dt.date], zone: dt.tzinfo) -> list[EnvironmentalLog]:
    return [
        EnvironmentalLog(
            timestamp=_at(day, 12, zone), pm2_5=round(rng.uniform(5, 35), 1), aqi=round(rng.uniform(20, 90)),
            pressure_mmHg=round(rng.gauss(755, 4), 1), pressure_delta_24h=round(rng.gauss(0, 3), 1), source=DEMO,
        )
        for day in days
    ]


def _symptom(rng: random.Random, day: dt.date, pressure_delta: float) -> HealthJournal | None:
    severity = min(10, max(0, round(2 - 0.8 * pressure_delta + rng.gauss(0, 0.6))))
    if severity == 0:
        return None
    return HealthJournal(entry_date=day, category="symptom", title="Headache", severity_1_10=severity,
                         body_location="head", source=DEMO)


def _metrics(rng: random.Random, days: list[dt.date], caffeine: dict[dt.date, float], magnesium: set[dt.date]) -> list[DailyMetric]:
    rows = []
    for index, day in enumerate(days):
        yesterday = days[index - 1] if index else None
        hrv = 62 - 0.1 * (caffeine[yesterday] if yesterday else 0) + rng.gauss(0, 2)
        deep = 70 + (14 if yesterday in magnesium else 0) + rng.gauss(0, 4)
        rows.append(DailyMetric(
            metric_date=day, hrv_sdnn=round(hrv, 1), sleep_deep_min=round(deep), sleep_total_min=round(rng.gauss(450, 25)),
            resting_hr=round(rng.gauss(58, 2), 1), steps=round(rng.gauss(8000, 1500)), source=DEMO,
        ))
    return rows


def _tap_tests(rng: random.Random, days: list[dt.date], zone: dt.tzinfo) -> list[CnsTest]:
    prior: list[tuple[dt.datetime, int]] = []
    tests = []
    for day in days:
        moment, taps = _at(day, 9, zone), round(rng.gauss(52, 3))
        deviation, _, _ = baseline_deviation(taps, moment, prior)
        tests.append(CnsTest(timestamp=moment, tap_count_10s=taps, baseline_dev_pct=deviation, source=DEMO))
        prior.append((moment, taps))
    return tests


LAB_RESULTS = [("25-OH Vitamin D", 24.0, "ng/mL", 30.0, 100.0), ("Ferritin", 85.0, "ng/mL", 30.0, 400.0)]


def _biomarkers(report_id: int) -> list[Biomarker]:
    markers = []
    for name, value, unit, low, high in LAB_RESULTS:
        key, display, _ = marker_identity(name)
        markers.append(Biomarker(report_id=report_id, marker_key=key, display_name=display, raw_name=name, value=value,
                                 unit=unit, ref_min=low, ref_max=high, is_out_of_range=is_out_of_range(value, low, high),
                                 source=DEMO))
    return markers


# (date, volume cm³, largest nodule mm, TI-RADS, verified); the last scan is added relative to today
THYROID_SCANS = [
    (dt.date(2022, 3, 14), 8.2, 4.0, 3, True), (dt.date(2023, 4, 3), 9.1, 5.0, 3, True),
    (dt.date(2024, 5, 20), 10.4, 7.0, 3, True), (dt.date(2025, 4, 8), 11.6, 9.0, 4, False),
]
KIDNEY_SCANS = [(dt.date(2023, 6, 12), 10.4, 10.8, True), (dt.date(2025, 6, 18), 10.3, 10.9, False)]


def _record(title: str, day: dt.date, details: str, key: str) -> MedicalRecord:
    return MedicalRecord(title=title, record_type="imaging", record_date=day, details=details, source=DEMO,
                         external_id=key)


def _scan_rows(record_id: int, organ: str, values: list[tuple[str, str, float | str, str]], verified: bool) -> list:
    origin = "manual" if verified else "rule"
    rows: list = [RecordOrgan(record_id=record_id, organ_key=organ, origin=origin)]
    for param, side, value, unit in values:
        number = isinstance(value, (int, float))
        rows.append(ScanMeasurement(record_id=record_id, organ_key=organ, param_key=param, side=side,
                                    value=value if number else None, value_text=None if number else value,
                                    unit=unit, origin=origin, verified=verified))
    return rows


def _organ_scans(session: Session, today: dt.date) -> None:
    last = today - dt.timedelta(days=45)
    thyroid = [*THYROID_SCANS, (last, 12.9, 11.0, 4, False)]
    latest = None
    for index, (day, volume, nodule, tirads, verified) in enumerate(thyroid):
        record = _record("Thyroid ultrasound", day, f"Thyroid gland. Total volume: {volume} cm³. Synthetic demo report.",
                         f"demo-thyroid-{index}")
        session.add(record)
        session.flush()
        half = round(volume / 2, 1)
        session.add_all(_scan_rows(record.id, "thyroid", [
            ("volume_total", "", volume, "cm³"), ("volume_lobe", "right", half, "cm³"),
            ("volume_lobe", "left", round(volume - half, 1), "cm³"), ("nodule_count", "", 1, "count"),
            ("nodule_max_mm", "", nodule, "mm"), ("tirads", "", tirads, "score"),
            ("echogenicity", "", "homogeneous" if tirads == 3 else "slightly decreased", ""),
        ], verified))
        latest = record
    for index, (day, right, left, verified) in enumerate(KIDNEY_SCANS):
        record = _record("Kidney ultrasound", day, f"Kidneys: right {right} cm, left {left} cm. Synthetic demo report.",
                         f"demo-kidney-{index}")
        session.add(record)
        session.flush()
        session.add_all(_scan_rows(record.id, "kidneys", [
            ("length_cm", "right", right, "cm"), ("length_cm", "left", left, "cm"),
            ("parenchyma_mm", "right", 17.0, "mm"), ("parenchyma_mm", "left", 16.0, "mm"),
        ], verified))
    course = Medication(name="Demo thyroid support", dosage="25 mcg daily", start_date=dt.date(2025, 5, 1),
                        end_date=dt.date(2025, 7, 31),  # finished, so it never shows up as a running course
                        target_marker_key="tsh", notes="Synthetic demo course.", source=DEMO, external_id="demo-course")
    session.add(course)
    session.flush()
    session.add(RecordMedication(record_id=latest.id, medication_id=course.id))


def demo_counts(session: Session) -> dict[str, int]:
    return {
        table.__name__: session.exec(select(func.count()).select_from(table).where(table.source == DEMO)).one()
        for table in DEMO_TABLES
    }


def _remove_record_children(session: Session) -> None:
    """Everything hanging off a demo record or demo medication goes with it, so nothing is left pointing nowhere."""
    records = select(MedicalRecord.id).where(MedicalRecord.source == DEMO)
    for table in RECORD_CHILDREN:
        session.exec(delete(table).where(table.record_id.in_(records)))
    session.exec(delete(RecordMedication).where(RecordMedication.medication_id.in_(
        select(Medication.id).where(Medication.source == DEMO))))
    session.exec(update(LabReport).where(LabReport.record_id.in_(records)).values(record_id=None))


def remove_demo(session: Session) -> dict[str, int]:
    removed = demo_counts(session)
    _remove_record_children(session)
    for table in DEMO_TABLES:  # biomarkers first: they point at the demo lab report
        session.exec(delete(table).where(table.source == DEMO))
    for table in DERIVED_TABLES:
        session.exec(delete(table))
    session.exec(delete(BriefingCache).where(BriefingCache.source == DEMO))
    session.exec(delete(AppSetting).where(AppSetting.key == REPORT_KEY))
    session.commit()
    return removed


def seed_demo(session: Session, today: dt.date) -> dict[str, int]:
    """Replace any earlier demo rows with a fresh, reproducible set ending on `today`."""
    remove_demo(session)
    rng, zone = random.Random(SEED), app_settings.configured_zone(session)
    days = [today - dt.timedelta(days=DAYS - 1 - i) for i in range(DAYS)]
    logs, caffeine, magnesium = _daily_logs(rng, days, zone)
    environment = _environment(rng, days, zone)
    symptoms = [_symptom(rng, e.timestamp.astimezone(zone).date(), e.pressure_delta_24h) for e in environment]
    taken = {row.metric_date for row in session.exec(select(DailyMetric))}
    session.add_all(logs + environment + [s for s in symptoms if s] + _tap_tests(rng, days, zone))
    session.add_all(m for m in _metrics(rng, days, caffeine, magnesium) if m.metric_date not in taken)
    report = LabReport(test_date=today - dt.timedelta(days=20), lab_name="Demo Lab", source=DEMO)
    session.add(report)
    session.flush()
    session.add_all(_biomarkers(report.id))
    _organ_scans(session, today)
    session.commit()
    return demo_counts(session)
