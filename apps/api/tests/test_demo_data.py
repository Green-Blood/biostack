import datetime as dt

from sqlmodel import select

from db.models import (
    Biomarker, BriefingCache, CnsTest, CorrelationCache, DailyMetric, EnvironmentalLog, HealthJournal, LabReport,
    SupplementLog,
)
from services.correlation_store import load_correlations, recompute
from services.demo_data import PLANTED_LAGS, demo_counts, remove_demo, seed_demo

TODAY = dt.date(2026, 3, 10)
DEMO_TABLES = (SupplementLog, DailyMetric, HealthJournal, CnsTest, EnvironmentalLog, LabReport, Biomarker)


def test_every_seeded_row_is_tagged_demo(session):
    seed_demo(session, TODAY)
    for table in DEMO_TABLES:
        rows = session.exec(select(table)).all()
        assert rows and all(row.source == "demo" for row in rows), table.__name__


def test_seeding_twice_does_not_duplicate_rows(session):
    first = seed_demo(session, TODAY)
    assert seed_demo(session, TODAY) == first == demo_counts(session)


def test_removal_deletes_only_demo_rows_and_the_caches_built_from_them(session):
    seed_demo(session, TODAY)
    recompute(session)
    session.add(SupplementLog(timestamp=dt.datetime(2026, 3, 9, 8, tzinfo=dt.timezone.utc), item_name="Zinc", source="manual"))
    session.add(DailyMetric(metric_date=dt.date(2020, 1, 1), hrv_sdnn=44.0, source="manual"))
    session.add(BriefingCache(briefing_date=TODAY, bullets=["a", "b", "c"], source="demo"))
    session.commit()
    removed = remove_demo(session)
    assert removed["SupplementLog"] > 0
    assert [s.item_name for s in session.exec(select(SupplementLog))] == ["Zinc"]
    assert [m.metric_date for m in session.exec(select(DailyMetric))] == [dt.date(2020, 1, 1)]
    for table in (HealthJournal, CnsTest, EnvironmentalLog, LabReport, Biomarker, CorrelationCache, BriefingCache):
        assert session.exec(select(table)).all() == [], table.__name__
    assert sum(demo_counts(session).values()) == 0


def test_seeding_never_overwrites_a_real_daily_metric(session):
    session.add(DailyMetric(metric_date=TODAY, hrv_sdnn=44.0, source="manual"))
    session.commit()
    seed_demo(session, TODAY)
    kept = session.get(DailyMetric, TODAY)
    assert kept.source == "manual" and kept.hrv_sdnn == 44.0


def test_the_analyzer_recovers_the_planted_effects_and_nothing_else(session):
    seed_demo(session, TODAY)
    recompute(session)
    found = {(c.trigger_key, c.target_metric): c for c in load_correlations(session)}
    assert set(found) == set(PLANTED_LAGS)
    for (trigger, target), planted in PLANTED_LAGS.items():
        assert found[(trigger, target)].lag_hours == planted.lag_hours
        assert (found[(trigger, target)].correlation_score < 0) == (planted.sign < 0)


def test_demo_counts_report_each_table(session):
    assert sum(demo_counts(session).values()) == 0
    seed_demo(session, TODAY)
    counts = demo_counts(session)
    assert counts["DailyMetric"] == 60 and counts["Biomarker"] >= 1


def test_seeding_and_removing_keep_a_real_briefing(session):
    yesterday = TODAY - dt.timedelta(days=1)
    session.add(BriefingCache(briefing_date=yesterday, bullets=["a", "b", "c"], source="real"))
    session.add(BriefingCache(briefing_date=TODAY, bullets=["x", "y", "z"], source="demo"))
    session.commit()
    seed_demo(session, TODAY)
    assert [b.briefing_date for b in session.exec(select(BriefingCache))] == [yesterday]
    remove_demo(session)
    assert [b.briefing_date for b in session.exec(select(BriefingCache))] == [yesterday]
