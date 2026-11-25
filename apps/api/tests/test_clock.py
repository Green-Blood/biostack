import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from services import app_settings, clock
from services.clock import local_zone
from services.daily_series import _local_day
from services.half_life_engine import bedtime_moment

NEW_YORK = ZoneInfo("America/New_York")
UTC = dt.timezone.utc


def test_the_system_zone_is_a_real_iana_zone_that_tests_can_replace(monkeypatch):
    monkeypatch.setattr(clock, "system_zone", lambda: NEW_YORK)
    assert local_zone() is NEW_YORK


def test_a_configured_timezone_overrides_the_system_zone(monkeypatch):
    monkeypatch.setattr(clock, "system_zone", lambda: NEW_YORK)
    assert local_zone("Europe/Berlin") == ZoneInfo("Europe/Berlin")
    assert local_zone("") is NEW_YORK


def test_the_zone_comes_from_the_saved_settings(session, monkeypatch):
    monkeypatch.setattr(clock, "system_zone", lambda: NEW_YORK)
    assert app_settings.configured_zone(session) is NEW_YORK
    app_settings.save_settings(session, app_settings.UserSettings(timezone="Asia/Tokyo"))
    assert app_settings.configured_zone(session) == ZoneInfo("Asia/Tokyo")


@pytest.mark.parametrize("day, utc_hour_next_day_or_same", [
    (dt.date(2025, 3, 8), dt.datetime(2025, 3, 9, 4, tzinfo=UTC)),    # before spring forward: UTC-5
    (dt.date(2025, 3, 9), dt.datetime(2025, 3, 10, 3, tzinfo=UTC)),   # the spring-forward day ends at UTC-4
    (dt.date(2025, 11, 1), dt.datetime(2025, 11, 2, 3, tzinfo=UTC)),  # before fall back: UTC-4
    (dt.date(2025, 11, 2), dt.datetime(2025, 11, 3, 4, tzinfo=UTC)),  # the fall-back day ends at UTC-5
])
def test_bedtime_follows_daylight_saving(monkeypatch, day, utc_hour_next_day_or_same):
    monkeypatch.setattr(clock, "system_zone", lambda: NEW_YORK)
    assert bedtime_moment(day, "23:00", local_zone()) == utc_hour_next_day_or_same


@pytest.mark.parametrize("utc_moment, local_day", [
    (dt.datetime(2025, 3, 10, 3, 30, tzinfo=UTC), dt.date(2025, 3, 9)),   # 23:30 EDT is still the 9th
    (dt.datetime(2025, 3, 10, 4, 30, tzinfo=UTC), dt.date(2025, 3, 10)),  # 00:30 EDT
    (dt.datetime(2025, 3, 9, 4, 30, tzinfo=UTC), dt.date(2025, 3, 8)),    # 23:30 EST on the 8th
    (dt.datetime(2025, 11, 3, 4, 30, tzinfo=UTC), dt.date(2025, 11, 2)),  # 23:30 EST on the 2nd
    (dt.datetime(2025, 11, 3, 5, 30, tzinfo=UTC), dt.date(2025, 11, 3)),
    (dt.datetime(2025, 11, 2, 3, 30, tzinfo=UTC), dt.date(2025, 11, 1)),  # 23:30 EDT on the 1st
])
def test_entries_near_midnight_land_on_the_right_local_day(monkeypatch, utc_moment, local_day):
    monkeypatch.setattr(clock, "system_zone", lambda: NEW_YORK)
    assert _local_day(utc_moment, local_zone()) == local_day
