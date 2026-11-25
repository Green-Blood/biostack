import datetime as dt

from db.models import DailyMetric, EnvironmentalLog, HealthJournal, SupplementLog
from services.clock import local_zone
from services.daily_series import build_predictors, build_targets

ZONE = local_zone()
DAY = dt.date(2026, 3, 10)


def _local(day: dt.date, hour: int) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour), tzinfo=ZONE).astimezone(dt.timezone.utc)


def _next(days: int) -> dt.date:
    return DAY + dt.timedelta(days=days)


def test_targets_come_from_daily_metrics_and_skip_missing_values(session):
    session.add(DailyMetric(metric_date=DAY, hrv_sdnn=55.0, sleep_deep_min=70.0))
    session.add(DailyMetric(metric_date=_next(1), hrv_sdnn=48.0))
    session.commit()
    targets = build_targets(session)
    assert targets["hrv_sdnn"] == {DAY: 55.0, _next(1): 48.0}
    assert targets["sleep_deep_min"] == {DAY: 70.0}


def test_symptom_severity_is_the_daily_maximum_with_zero_on_quiet_days(session):
    session.add(HealthJournal(entry_date=DAY, category="symptom", title="Headache", severity_1_10=4))
    session.add(HealthJournal(entry_date=DAY, category="symptom", title="Nausea", severity_1_10=7))
    session.add(HealthJournal(entry_date=_next(2), category="symptom", title="Headache", severity_1_10=3))
    session.add(HealthJournal(entry_date=_next(2), category="note", title="Walked", severity_1_10=None))
    session.commit()
    assert build_targets(session)["symptom_severity"] == {DAY: 7.0, _next(1): 0.0, _next(2): 3.0}


def test_no_journal_means_no_symptom_target(session):
    assert "symptom_severity" not in build_targets(session)


def test_caffeine_at_bedtime_carries_over_from_the_previous_evening(session):
    session.add(SupplementLog(timestamp=_local(DAY, 20), item_name="Caffeine", dosage=200, category="stimulant"))
    session.add(SupplementLog(timestamp=_local(_next(2), 8), item_name="Magnesium", dosage=400, category="supplement"))
    session.commit()
    series, variables = build_predictors(session, "23:00", ZONE)
    caffeine = series["caffeine_at_bedtime"]
    assert round(caffeine[DAY]) == round(200 * 0.5 ** (3 / 5))
    assert round(caffeine[_next(1)], 1) == round(200 * 0.5 ** (27 / 5), 1)
    assert caffeine[_next(2)] < caffeine[_next(1)]
    assert variables["caffeine_at_bedtime"].kind == "trigger"


def test_supplements_become_daily_protector_flags_and_other_stimulants_triggers(session):
    session.add(SupplementLog(timestamp=_local(DAY, 9), item_name="Magnesium", category="supplement"))
    session.add(SupplementLog(timestamp=_local(_next(2), 9), item_name="Magnesium", category="supplement"))
    session.add(SupplementLog(timestamp=_local(_next(1), 9), item_name="Guarana", category="stimulant"))
    session.commit()
    series, variables = build_predictors(session, "23:00", ZONE)
    assert series["protector:magnesium"] == {DAY: 1.0, _next(1): 0.0, _next(2): 1.0}
    assert variables["protector:magnesium"].kind == "protector"
    assert series["trigger:guarana"][_next(1)] == 1.0
    assert variables["trigger:guarana"].label == "Guarana taken"


def test_medications_are_not_used_as_predictors(session):
    session.add(SupplementLog(timestamp=_local(DAY, 9), item_name="Ibuprofen", category="medication"))
    session.commit()
    series, _ = build_predictors(session, "23:00", ZONE)
    assert series == {}


def test_environment_readings_are_averaged_per_local_day(session):
    session.add(EnvironmentalLog(timestamp=_local(DAY, 8), pm2_5=10.0, pressure_delta_24h=-2.0))
    session.add(EnvironmentalLog(timestamp=_local(DAY, 14), pm2_5=20.0, pressure_delta_24h=None))
    session.commit()
    series, variables = build_predictors(session, "23:00", ZONE)
    assert series["pm2_5"] == {DAY: 15.0}
    assert series["pressure_delta_24h"] == {DAY: -2.0}
    assert variables["pm2_5"].kind == "trigger"
