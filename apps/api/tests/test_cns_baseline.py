import datetime as dt

import pytest

from services.cns_baseline import MIN_PRIOR_TESTS, baseline_deviation

NOW = dt.datetime(2026, 11, 10, 9, 0, tzinfo=dt.timezone.utc)


def _prior(*pairs):
    return [(NOW - dt.timedelta(days=days), taps) for days, taps in pairs]


def test_deviation_is_percent_from_the_mean_of_prior_tests():
    prior = _prior((1, 60), (2, 60), (3, 60))
    assert baseline_deviation(66, NOW, prior) == pytest.approx((10.0, 60.0, 3))
    assert baseline_deviation(54, NOW, prior)[0] == pytest.approx(-10.0)


def test_fewer_than_three_prior_tests_gives_no_baseline():
    assert MIN_PRIOR_TESTS == 3
    assert baseline_deviation(60, NOW, _prior((1, 60), (2, 62))) == (None, None, 2)
    assert baseline_deviation(60, NOW, []) == (None, None, 0)


def test_only_the_previous_14_days_count():
    prior = _prior((1, 60), (2, 60), (3, 60), (15, 200), (30, 200))
    assert baseline_deviation(60, NOW, prior) == (0.0, 60.0, 3)


def test_tests_after_the_new_one_are_ignored():
    prior = _prior((1, 60), (2, 60), (3, 60)) + [(NOW + dt.timedelta(hours=1), 5)]
    assert baseline_deviation(60, NOW, prior)[2] == 3
