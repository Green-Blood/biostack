"""Pure trend maths. No AI, no fitted lines: just points, deltas and range position."""
from dataclasses import dataclass


@dataclass
class Point:
    date: str
    value: float
    ref_min: float | None = None
    ref_max: float | None = None


@dataclass
class Delta:
    from_date: str
    to_date: str
    abs: float
    pct: float | None
    toward_range: bool | None
    stayed_in_range: bool = False


def distance_from_range(p: Point) -> float | None:
    if p.ref_min is None and p.ref_max is None:
        return None
    if p.ref_min is not None and p.value < p.ref_min:
        return p.ref_min - p.value
    if p.ref_max is not None and p.value > p.ref_max:
        return p.value - p.ref_max
    return 0.0


def compute_deltas(points: list[Point]) -> list[Delta]:
    out = []
    for a, b in zip(points, points[1:]):
        change = b.value - a.value
        da, db = distance_from_range(a), distance_from_range(b)
        toward = None if da is None or db is None or da == db else db < da
        out.append(Delta(a.date, b.date, change, None if a.value == 0 else change / abs(a.value) * 100, toward,
                         stayed_in_range=da == 0 and db == 0))
    return out


def pct_of_range(value: float, ref_min: float | None, ref_max: float | None) -> float | None:
    """0 = ref_min, 1 = ref_max; outside the range goes below 0 / above 1."""
    if ref_min is None or ref_max is None or ref_max <= ref_min:
        return None
    return (value - ref_min) / (ref_max - ref_min)
