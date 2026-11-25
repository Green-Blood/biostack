"""A tap test is judged against the mean of the previous 14 days of tests, once there are at least three."""
import datetime as dt
from collections.abc import Iterable

from services.half_life_engine import as_utc

BASELINE_DAYS = 14
MIN_PRIOR_TESTS = 3


def baseline_deviation(
    tap_count: int, moment: dt.datetime, prior: Iterable[tuple[dt.datetime, int]]
) -> tuple[float | None, float | None, int]:
    """Return (deviation percent, baseline mean, samples used); the first two are None below the minimum."""
    moment = as_utc(moment)
    window_start = moment - dt.timedelta(days=BASELINE_DAYS)
    counts = [taps for stamp, taps in prior if window_start <= as_utc(stamp) < moment]
    if len(counts) < MIN_PRIOR_TESTS:
        return None, None, len(counts)
    mean = sum(counts) / len(counts)
    return (tap_count - mean) / mean * 100 if mean else None, mean, len(counts)
