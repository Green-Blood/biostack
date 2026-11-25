import datetime as dt

from sqlmodel import select

from config import settings
from db.models import BodyMeasurement, DailyMetric, SleepSession, SleepStage, Workout
from services import wearable_ingest as wi
from services.wearable_ingest import SleepIn, StageIn, UpsertCount, WorkoutIn

DAY = dt.date(2026, 11, 10)
T0 = dt.datetime(2026, 11, 9, 20, 0, tzinfo=dt.timezone.utc)


def _sleep(ext="s1", minutes=420, **kw):
    base = dict(external_id=ext, start_utc=T0, end_utc=T0 + dt.timedelta(minutes=minutes), tz_offset_min=300,
                wake_date=DAY, duration_min=minutes, deep_min=80, rem_min=90, light_min=230, awake_min=20,
                efficiency=92.0, sleep_type="main", is_main=True, device_id="dev1")
    base.update(kw)
    return SleepIn(**base)


def _stages(n=3):
    return [StageIn(external_id=f"st{i}", start_utc=T0 + dt.timedelta(minutes=i * 10),
                    end_utc=T0 + dt.timedelta(minutes=i * 10 + 10), stage="light") for i in range(n)]


def test_import_never_replaces_manual_or_sync_field(session):
    session.add(DailyMetric(metric_date=DAY, hrv_sdnn=40.0, source="manual", field_sources={"hrv_sdnn": "manual"}))
    session.commit()
    written = wi.ingest_daily(session, {DAY: {"hrv_sdnn": 99.0, "steps": 5000.0}}, "samsung_export")
    row = session.get(DailyMetric, DAY)
    assert written == 1
    assert row.hrv_sdnn == 40.0 and row.steps == 5000
    assert row.field_sources == {"hrv_sdnn": "manual", "steps": "samsung_export"}


def test_import_never_replaces_health_sync_field(session):
    session.add(DailyMetric(metric_date=DAY, resting_hr=50.0, source="health_sync", field_sources={"resting_hr": "health_sync"}))
    session.commit()
    assert wi.ingest_daily(session, {DAY: {"resting_hr": 70.0}}, "samsung_export") == 0
    assert session.get(DailyMetric, DAY).resting_hr == 50.0


def test_import_overwrites_own_previous_value(session):
    wi.ingest_daily(session, {DAY: {"steps": 100.0}}, "samsung_export")
    assert wi.ingest_daily(session, {DAY: {"steps": 200.0}}, "samsung_export") == 1
    row = session.get(DailyMetric, DAY)
    assert row.steps == 200 and row.field_sources == {"steps": "samsung_export"}


def test_import_writes_new_columns_and_fills_empty_legacy_field(session):
    session.add(DailyMetric(metric_date=DAY, steps=10, source="health_sync"))  # legacy row, no field_sources
    session.commit()
    wi.ingest_daily(session, {DAY: {"hrv_rmssd": 33.0, "steps": 999.0}}, "samsung_export")
    row = session.get(DailyMetric, DAY)
    assert row.hrv_rmssd == 33.0
    assert row.steps == 10  # legacy field attributed to the row source, protected


def test_import_replaces_demo_row(session):
    session.add(DailyMetric(metric_date=DAY, steps=1, resting_hr=60, source="demo"))
    session.commit()
    wi.ingest_daily(session, {DAY: {"steps": 7.0}}, "samsung_export")
    row = session.get(DailyMetric, DAY)
    assert row.resting_hr is None and row.steps == 7 and row.source == "samsung_export"


def test_complete_reimport_clears_own_fields_no_longer_derived(session):
    other = DAY - dt.timedelta(days=1)
    untouched = DAY - dt.timedelta(days=2)
    wi.ingest_daily(session, {DAY: {"hrv_sdnn": 40.0, "resting_hr": 50.0, "steps": 100.0},
                              other: {"skin_temp_delta": 0.3}, untouched: {"steps": 5.0}}, "samsung_export")
    row = session.get(DailyMetric, DAY)
    row.spo2_avg, row.field_sources = 97.0, {**row.field_sources, "spo2_avg": "health_sync"}
    session.add(row)
    session.commit()
    wi.ingest_daily(session, {DAY: {"steps": 200.0}, other: {}}, "samsung_export", complete=True)
    row = session.get(DailyMetric, DAY)
    assert (row.hrv_sdnn, row.resting_hr, row.steps, row.spo2_avg) == (None, None, 200, 97.0)
    assert row.field_sources == {"steps": "samsung_export", "spo2_avg": "health_sync"}
    assert session.get(DailyMetric, other) is None  # nothing left on the day: the row goes
    assert session.get(DailyMetric, untouched).steps == 5  # a day not covered is left alone


def test_partial_ingest_keeps_fields_it_does_not_send(session):
    wi.ingest_daily(session, {DAY: {"hrv_sdnn": 40.0, "steps": 100.0}}, "samsung_export")
    wi.ingest_daily(session, {DAY: {"steps": 200.0}}, "samsung_export")
    assert session.get(DailyMetric, DAY).hrv_sdnn == 40.0


def test_complete_reimport_never_deletes_a_demo_day_it_has_nothing_for(session):
    session.add(DailyMetric(metric_date=DAY, steps=1, source="demo"))
    session.commit()
    wi.ingest_daily(session, {DAY: {}}, "samsung_export", complete=True)
    assert session.get(DailyMetric, DAY).steps == 1


def test_sleep_group_is_skipped_when_another_source_holds_part_of_it(session):
    session.add(DailyMetric(metric_date=DAY, sleep_total_min=400.0, hrv_rmssd=30.0, source="health_sync",
                            field_sources={"sleep_total_min": "health_sync", "hrv_rmssd": "health_sync"}))
    session.commit()
    night = {"sleep_total_min": 420.0, "sleep_deep_min": 60.0, "sleep_rem_min": 90.0, "sleep_light_min": 250.0,
             "sleep_awake_min": 20.0, "sleep_efficiency": 91.0, "hrv_sdnn": 44.0, "hrv_rmssd": 35.0,
             "resting_hr": 52.0}
    wi.ingest_daily(session, {DAY: night}, "samsung_export", complete=True)
    row = session.get(DailyMetric, DAY)
    assert row.sleep_total_min == 400.0
    assert (row.sleep_deep_min, row.sleep_rem_min, row.sleep_light_min, row.sleep_awake_min, row.sleep_efficiency) == (None,) * 5
    assert (row.hrv_sdnn, row.hrv_rmssd) == (None, 30.0)
    assert row.resting_hr == 52.0
    assert row.field_sources == {"sleep_total_min": "health_sync", "hrv_rmssd": "health_sync", "resting_hr": "samsung_export"}


def test_sleep_group_blocked_later_drops_own_older_group_fields(session):
    night = {"sleep_total_min": 420.0, "sleep_deep_min": 60.0}
    wi.ingest_daily(session, {DAY: night}, "samsung_export")
    row = session.get(DailyMetric, DAY)
    row.sleep_total_min, row.field_sources = 380.0, {**row.field_sources, "sleep_total_min": "manual"}
    session.add(row)
    session.commit()
    wi.ingest_daily(session, {DAY: night}, "samsung_export", complete=True)
    row = session.get(DailyMetric, DAY)
    assert (row.sleep_total_min, row.sleep_deep_min) == (380.0, None)  # one night, one source


def test_upsert_sleep_updates_changed_and_is_idempotent(session):
    first = wi.ingest_sleep(session, [_sleep()], {"s1": _stages(3)}, "samsung_export")
    assert first == UpsertCount(1, 0, 0)
    assert wi.ingest_sleep(session, [_sleep()], {"s1": _stages(3)}, "samsung_export") == UpsertCount(0, 0, 1)
    assert wi.ingest_sleep(session, [_sleep(minutes=400)], {"s1": _stages(2)}, "samsung_export") == UpsertCount(0, 1, 0)
    assert len(session.exec(select(SleepSession)).all()) == 1
    assert session.exec(select(SleepSession)).one().duration_min == 400
    assert len(session.exec(select(SleepStage)).all()) == 2


def test_workout_upsert(session):
    w = WorkoutIn(external_id="w1", start_utc=T0, end_utc=T0 + dt.timedelta(minutes=30), tz_offset_min=300, local_date=DAY,
                  type_code=1002, duration_min=30, kcal=200, distance_m=3000, hr_avg=120, hr_max=150, device_id="d")
    assert wi.ingest_workouts(session, [w], "samsung_export") == UpsertCount(1, 0, 0)
    assert wi.ingest_workouts(session, [w], "samsung_export") == UpsertCount(0, 0, 1)
    w2 = WorkoutIn(**{**w.__dict__, "kcal": 250})
    assert wi.ingest_workouts(session, [w2], "samsung_export") == UpsertCount(0, 1, 0)
    assert session.exec(select(Workout)).one().kcal == 250


def test_body_last_weighin_of_day_wins_and_manual_guarded(session):
    session.add(BodyMeasurement(measured_on=DAY, kind="waist", value=80, source="manual"))
    session.commit()
    n = wi.ingest_body(session, {DAY: {"weight": 70.5, "waist": 99.0}}, "samsung_export")
    rows = {r.kind: (r.value, r.source) for r in session.exec(select(BodyMeasurement)).all()}
    assert n == 1
    assert rows == {"waist": (80, "manual"), "weight": (70.5, "samsung_export")}


def test_body_import_never_replaces_sync_csv_or_manual_rows(session):
    other = DAY - dt.timedelta(days=1)
    session.add(BodyMeasurement(measured_on=DAY, kind="weight", value=80.0, source="sync"))
    session.add(BodyMeasurement(measured_on=DAY, kind="body_fat_pct", value=20.0, source="csv"))
    session.add(BodyMeasurement(measured_on=DAY, kind="waist", value=90.0, source="manual"))
    session.add(BodyMeasurement(measured_on=other, kind="weight", value=71.0, source="samsung_export"))
    session.commit()
    n = wi.ingest_body(session, {DAY: {"weight": 70.5, "body_fat_pct": 25.0, "waist": 99.0, "muscle_kg": 30.0},
                                 other: {"weight": 72.0}}, "samsung_export")
    rows = {(r.measured_on, r.kind): (r.value, r.source) for r in session.exec(select(BodyMeasurement)).all()}
    assert n == 2
    assert rows == {(DAY, "weight"): (80.0, "sync"), (DAY, "body_fat_pct"): (20.0, "csv"),
                    (DAY, "waist"): (90.0, "manual"), (DAY, "muscle_kg"): (30.0, "samsung_export"),
                    (other, "weight"): (72.0, "samsung_export")}


def test_health_sync_still_works_and_records_field_sources(client, session):
    r = client.post("/api/v1/health-sync", headers={"X-API-Key": settings.api_secret_key},
                    json={"date": "2026-11-10", "steps": 1234, "resting_hr": 55})
    assert r.status_code == 200, r.text
    row = session.get(DailyMetric, DAY)
    assert row.field_sources == {"steps": "health_sync", "resting_hr": "health_sync"}
