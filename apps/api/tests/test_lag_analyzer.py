import datetime as dt
import random

import pytest

from services.lag_analyzer import MIN_OVERLAP_DAYS, analyze, correlate, shifted_pairs

START = dt.date(2026, 1, 1)


def _days(count: int) -> list[dt.date]:
    return [START + dt.timedelta(days=i) for i in range(count)]


def _series(values: list[float]) -> dict[dt.date, float]:
    return dict(zip(_days(len(values)), values))


def _planted(count: int = 40, lag_days: int = 1, slope: float = -2.0, seed: int = 7):
    rng = random.Random(seed)
    predictor = [rng.gauss(100, 30) for _ in range(count)]
    target = [60 + slope * predictor[max(i - lag_days, 0)] / 10 + rng.gauss(0, 0.5) for i in range(count)]
    return _series(predictor), _series(target)


def test_whole_day_lag_pairs_the_predictor_from_that_many_days_earlier():
    predictor, target = _series([1, 2, 3, 4]), _series([10, 20, 30, 40])
    x, y = shifted_pairs(predictor, target, lag_hours=24)
    assert x == [1, 2, 3] and y == [20, 30, 40]


def test_half_day_lag_interpolates_between_neighbouring_days():
    predictor, target = _series([0, 10, 20]), _series([5, 5, 5])
    x, y = shifted_pairs(predictor, target, lag_hours=12)
    assert x == [5.0, 15.0] and y == [5, 5]


def test_days_without_a_predictor_value_are_left_out():
    predictor = {START: 1.0, START + dt.timedelta(days=2): 3.0}
    target = _series([9, 9, 9])
    x, _ = shifted_pairs(predictor, target, lag_hours=0)
    assert x == [1.0, 3.0]


def test_correlate_reports_both_coefficients_with_p_values():
    predictor, target = _planted()
    result = correlate(predictor, target, lag_hours=24)
    assert result is not None
    assert result.pearson_r < -0.9 and result.pearson_p < 0.001
    assert result.spearman_r < -0.9 and result.spearman_p < 0.001
    assert result.n_days >= MIN_OVERLAP_DAYS


def test_correlate_needs_at_least_14_overlapping_days():
    predictor, target = _planted(count=MIN_OVERLAP_DAYS - 1, lag_days=0)
    assert correlate(predictor, target, lag_hours=0) is None


def test_correlate_ignores_a_flat_series():
    assert correlate(_series([5.0] * 30), _series(list(map(float, range(30)))), lag_hours=0) is None


def test_analyzer_recovers_the_planted_lag_and_sign():
    predictor, target = _planted(lag_days=1)
    result = analyze({"hrv": target}, {"caffeine": predictor})
    assert [(c.target, c.predictor, c.lag_hours) for c in result.correlations] == [("hrv", "caffeine", 24)]
    assert result.correlations[0].pearson_r < 0


def test_analyzer_recovers_a_two_day_lag():
    predictor, target = _planted(lag_days=2, slope=1.5, seed=3)
    (found,) = analyze({"hrv": target}, {"x": predictor}).correlations
    assert found.lag_hours == 48 and found.pearson_r > 0


def test_analyzer_ignores_noise():
    rng = random.Random(11)
    noise = {f"noise{i}": _series([rng.gauss(0, 1) for _ in range(40)]) for i in range(4)}
    target = _series([rng.gauss(0, 1) for _ in range(40)])
    result = analyze({"hrv": target}, noise)
    assert result.correlations == []
    assert result.targets[0].status == "ok" and result.targets[0].pairs_tested == 4 * 5


def test_target_with_too_few_days_is_insufficient_with_a_reason():
    predictor, target = _planted(count=9, lag_days=0)
    result = analyze({"hrv": target}, {"caffeine": predictor})
    report = result.targets[0]
    assert report.status == "insufficient_data" and report.days == 9
    assert "14" in report.reason and result.correlations == []


def test_target_without_any_overlapping_predictor_is_insufficient():
    _, target = _planted()
    far_away = {dt.date(2020, 1, 1) + dt.timedelta(days=i): float(i) for i in range(30)}
    report = analyze({"hrv": target}, {"x": far_away}).targets[0]
    assert report.status == "insufficient_data" and "overlap" in report.reason


def test_weaker_pairs_are_not_reported():
    rng = random.Random(5)
    predictor = [rng.gauss(0, 1) for _ in range(40)]
    target = [0.3 * p + rng.gauss(0, 1) for p in predictor]
    assert analyze({"t": _series(target)}, {"p": _series(predictor)}).correlations == []


@pytest.mark.parametrize("lag", [0, 12, 24, 36, 48])
def test_every_supported_lag_can_be_evaluated(lag):
    predictor, target = _planted()
    assert correlate(predictor, target, lag_hours=lag) is not None
