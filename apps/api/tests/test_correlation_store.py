import datetime as dt
import random

from sqlmodel import select

from db.models import CorrelationCache, DailyMetric, SupplementLog
from services.clock import local_zone
from services.correlation_store import load_correlations, load_report, recompute

ZONE = local_zone()
FIRST = dt.date(2026, 1, 1)


def _seed_caffeine_hrv(session, days: int = 40) -> None:
    rng = random.Random(1)
    for i in range(days):
        day = FIRST + dt.timedelta(days=i)
        hour = rng.choice([8, 21])
        stamp = dt.datetime.combine(day, dt.time(hour), tzinfo=ZONE).astimezone(dt.timezone.utc)
        session.add(SupplementLog(timestamp=stamp, item_name="Caffeine", dosage=200, category="stimulant"))
    session.commit()
    logs = session.exec(select(SupplementLog).order_by(SupplementLog.timestamp)).all()
    for i in range(days):
        day = FIRST + dt.timedelta(days=i)
        late = 1 if i > 0 and logs[i - 1].timestamp.replace(tzinfo=dt.timezone.utc).astimezone(ZONE).hour == 21 else 0
        session.add(DailyMetric(metric_date=day, hrv_sdnn=60 - 12 * late + rng.gauss(0, 1.5)))
    session.commit()


def test_recompute_stores_the_found_correlation_with_its_statistics(session):
    _seed_caffeine_hrv(session)
    recompute(session)
    (row,) = session.exec(select(CorrelationCache)).all()
    assert (row.target_metric, row.trigger_key, row.lag_hours) == ("hrv_sdnn", "caffeine_at_bedtime", 24)
    assert row.correlation_score < -0.5 and row.p_value < 0.05 and row.n_days >= 14
    assert row.confidence_pct == round((1 - row.p_value) * 100, 1)


def test_recompute_replaces_earlier_results(session):
    _seed_caffeine_hrv(session)
    recompute(session)
    recompute(session)
    assert len(session.exec(select(CorrelationCache)).all()) == 1


def test_report_lists_each_target_with_its_status(session):
    for i in range(5):
        session.add(DailyMetric(metric_date=FIRST + dt.timedelta(days=i), hrv_sdnn=50.0 + i))
    session.commit()
    recompute(session)
    report = load_report(session)
    assert report is not None and report.targets[0].target == "hrv_sdnn"
    assert report.targets[0].status == "insufficient_data" and "14" in report.targets[0].reason
    assert load_correlations(session) == []


def test_report_is_none_before_the_first_recompute(session):
    assert load_report(session) is None
