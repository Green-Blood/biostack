import datetime as dt
from zoneinfo import ZoneInfo

import tzlocal


def system_zone() -> ZoneInfo:
    """The computer's own IANA time zone (for example Europe/Berlin), so daylight saving follows its rules."""
    return tzlocal.get_localzone()


def local_zone(configured: str = "") -> dt.tzinfo:
    """The zone bedtime and "today" are read in: the owner's chosen IANA name, else the computer's zone."""
    return ZoneInfo(configured) if configured else system_zone()


def today(zone: dt.tzinfo | None = None) -> dt.date:
    """Today's date in the owner's zone. Services call this (as `clock.today`) so tests can pin the day."""
    return dt.datetime.now(zone or system_zone()).date()
