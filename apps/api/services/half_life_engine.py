"""First-order decay of logged doses: C(t) = C0 * 0.5 ** ((t - t0) / half_life), summed over doses."""
import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass

DEFAULT_HALF_LIFE_HOURS: dict[str, float] = {"caffeine": 5.0, "l-theanine": 1.5, "melatonin": 0.75}
FALLBACK_HALF_LIFE_HOURS = 5.0


@dataclass(frozen=True)
class Dose:
    timestamp: dt.datetime
    amount: float
    half_life_hours: float | None = None


def as_utc(moment: dt.datetime) -> dt.datetime:
    """SQLite hands back naive datetimes; everything stored is UTC."""
    return moment.replace(tzinfo=dt.timezone.utc) if moment.tzinfo is None else moment.astimezone(dt.timezone.utc)


def remaining_at(doses: Iterable[Dose], moment: dt.datetime, default_half_life: float) -> float:
    if default_half_life <= 0:
        raise ValueError("The default half-life must be above zero hours.")
    moment = as_utc(moment)
    total = 0.0
    for dose in doses:
        half_life = dose.half_life_hours or default_half_life
        elapsed_hours = (moment - as_utc(dose.timestamp)).total_seconds() / 3600
        if elapsed_hours >= 0:
            total += dose.amount * 0.5 ** (elapsed_hours / half_life)
    return total


def bedtime_moment(day: dt.date, bedtime: str, zone: dt.tzinfo) -> dt.datetime:
    try:
        hour, minute = (int(part) for part in bedtime.split(":"))
        local = dt.datetime.combine(day, dt.time(hour, minute), tzinfo=zone)
    except ValueError:
        raise ValueError("Bedtime must be written as HH:MM, for example 23:00.") from None
    return local.astimezone(dt.timezone.utc)


def at_bedtime(doses: Iterable[Dose], day: dt.date, bedtime: str, zone: dt.tzinfo, default_half_life: float) -> float:
    return remaining_at(doses, bedtime_moment(day, bedtime, zone), default_half_life)
