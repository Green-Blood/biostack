import datetime as dt

import pytest

from services.half_life_engine import DEFAULT_HALF_LIFE_HOURS, Dose, at_bedtime, bedtime_moment, remaining_at

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def test_one_half_life_later_half_remains():
    assert remaining_at([Dose(T0, 200)], T0 + dt.timedelta(hours=5), default_half_life=5) == pytest.approx(100)


def test_dose_just_taken_is_fully_present():
    assert remaining_at([Dose(T0, 200)], T0, default_half_life=5) == pytest.approx(200)


def test_multiple_doses_sum():
    doses = [Dose(T0, 200), Dose(T0 + dt.timedelta(hours=5), 100)]
    assert remaining_at(doses, T0 + dt.timedelta(hours=10), default_half_life=5) == pytest.approx(50 + 50)


def test_dose_after_t_is_ignored():
    assert remaining_at([Dose(T0 + dt.timedelta(hours=1), 200)], T0, default_half_life=5) == 0


def test_no_doses_or_zero_amount_is_zero():
    assert remaining_at([], T0, default_half_life=5) == 0
    assert remaining_at([Dose(T0, 0)], T0 + dt.timedelta(hours=1), default_half_life=5) == 0


def test_per_dose_half_life_overrides_default():
    doses = [Dose(T0, 100, half_life_hours=2)]
    assert remaining_at(doses, T0 + dt.timedelta(hours=2), default_half_life=5) == pytest.approx(50)


def test_naive_timestamps_are_read_as_utc():
    assert remaining_at([Dose(T0.replace(tzinfo=None), 100)], T0 + dt.timedelta(hours=5), default_half_life=5) == pytest.approx(50)


def test_non_positive_half_life_is_rejected():
    with pytest.raises(ValueError, match="half-life"):
        remaining_at([Dose(T0, 100)], T0, default_half_life=0)


def test_bedtime_moment_uses_the_given_zone():
    zone = dt.timezone(dt.timedelta(hours=3))
    assert bedtime_moment(dt.date(2026, 11, 10), "23:00", zone) == dt.datetime(2026, 11, 10, 20, 0, tzinfo=UTC)


def test_bedtime_rejects_bad_clock_text():
    with pytest.raises(ValueError, match="HH:MM"):
        bedtime_moment(dt.date(2026, 11, 10), "late", UTC)


def test_at_bedtime_counts_the_afternoon_coffee():
    doses = [Dose(dt.datetime(2026, 11, 10, 16, 30, tzinfo=UTC), 200, half_life_hours=6.5)]
    assert at_bedtime(doses, dt.date(2026, 11, 10), "23:00", UTC, default_half_life=5) == pytest.approx(100)


def test_caffeine_default_is_five_hours():
    assert DEFAULT_HALF_LIFE_HOURS["caffeine"] == 5
