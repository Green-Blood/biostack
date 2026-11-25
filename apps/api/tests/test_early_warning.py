import datetime as dt

from db.models import CnsTest, CorrelationCache, DailyMetric, EnvironmentalLog, SupplementLog
from services.clock import local_zone
from services.early_warning import FACTOR_WEIGHTS, assess_risk

ZONE = local_zone()
NOW = dt.datetime(2026, 3, 10, 12, 0, tzinfo=ZONE).astimezone(dt.timezone.utc)
TODAY = NOW.astimezone(ZONE).date()


def _hours_ago(hours: float) -> dt.datetime:
    return NOW - dt.timedelta(hours=hours)


def _baseline_days(session, hrv: float, deep: float) -> None:
    for back in range(2, 16):
        session.add(DailyMetric(metric_date=TODAY - dt.timedelta(days=back), hrv_sdnn=hrv, sleep_deep_min=deep))


def _bad_day(session) -> None:
    _baseline_days(session, hrv=60, deep=80)
    session.add(DailyMetric(metric_date=TODAY, hrv_sdnn=40, sleep_deep_min=40))
    session.add(EnvironmentalLog(timestamp=_hours_ago(2), pm2_5=60.0, pressure_delta_24h=-9.0))
    session.add(SupplementLog(timestamp=_hours_ago(15), item_name="Caffeine", dosage=300, category="stimulant"))
    session.add(CnsTest(timestamp=_hours_ago(3), tap_count_10s=40, baseline_dev_pct=-25.0))
    session.commit()


def _assess(session):
    return assess_risk(session, NOW, "23:00", ZONE)


def test_factor_weights_add_up_to_one_hundred():
    assert sum(FACTOR_WEIGHTS.values()) == 100


def test_without_data_there_is_no_score_and_a_reason(session):
    risk = _assess(session)
    assert risk.score is None and risk.alert is False and risk.level is None
    assert "log" in risk.reason.lower()
    assert all(not factor.has_data for factor in risk.factors)


def test_a_single_factor_is_not_enough_for_a_score(session):
    session.add(EnvironmentalLog(timestamp=_hours_ago(2), pm2_5=60.0))
    session.commit()
    risk = _assess(session)
    assert risk.score is None and "2" in risk.reason


def test_a_bad_day_scores_high_raises_the_alert_and_recommends_steps(session):
    _bad_day(session)
    risk = _assess(session)
    assert risk.score is not None and risk.score > 70
    assert risk.alert is True and risk.level == "high"
    assert risk.recommendations


def test_breakdown_points_add_up_to_the_score(session):
    _bad_day(session)
    risk = _assess(session)
    with_data = [factor for factor in risk.factors if factor.has_data]
    assert round(100 * sum(f.points for f in with_data) / sum(f.weight for f in with_data)) == risk.score
    assert all(0 <= factor.points <= factor.weight for factor in risk.factors)


def test_a_calm_day_scores_low_without_alert_or_recommendations(session):
    _baseline_days(session, hrv=60, deep=80)
    session.add(DailyMetric(metric_date=TODAY, hrv_sdnn=61, sleep_deep_min=82))
    session.add(EnvironmentalLog(timestamp=_hours_ago(2), pm2_5=5.0, pressure_delta_24h=0.5))
    session.commit()
    risk = _assess(session)
    assert risk.score == 0 and risk.level == "low" and risk.alert is False and risk.recommendations == []


def test_missing_factors_do_not_lower_the_score(session):
    session.add(EnvironmentalLog(timestamp=_hours_ago(2), pm2_5=60.0, pressure_delta_24h=-9.0))
    session.commit()
    risk = _assess(session)
    assert risk.score == 100
    assert {f.key for f in risk.factors if f.has_data} == {"pressure_drop", "air_quality"}


def test_a_baseline_needs_at_least_a_week_of_history(session):
    for back in range(2, 5):
        session.add(DailyMetric(metric_date=TODAY - dt.timedelta(days=back), hrv_sdnn=60, sleep_deep_min=80))
    session.add(DailyMetric(metric_date=TODAY, hrv_sdnn=30, sleep_deep_min=20))
    session.commit()
    factors = {f.key: f for f in _assess(session).factors}
    assert not factors["hrv_drop"].has_data and not factors["deep_sleep_drop"].has_data


def test_readings_older_than_48_hours_are_ignored(session):
    session.add(EnvironmentalLog(timestamp=_hours_ago(60), pm2_5=90.0, pressure_delta_24h=-12.0))
    session.commit()
    assert not any(f.has_data for f in _assess(session).factors)


def test_factors_backed_by_a_cached_correlation_are_marked_and_quoted(session):
    _bad_day(session)
    session.add(CorrelationCache(
        target_metric="hrv_sdnn", trigger_key="caffeine_at_bedtime", correlation_score=-0.8, lag_hours=24,
        confidence_pct=99.0, p_value=0.01, spearman_score=-0.7, spearman_p=0.01, n_days=40,
    ))
    session.commit()
    risk = _assess(session)
    caffeine = next(f for f in risk.factors if f.key == "late_caffeine")
    assert caffeine.seen_in_days == 40
    assert any("More caffeine late in the day goes with lower HRV the next day" in text and "40 days" in text
               for text in risk.recommendations)
    assert not any("r =" in text for text in risk.recommendations)
    assert next(f for f in risk.factors if f.key == "air_quality").seen_in_days is None
