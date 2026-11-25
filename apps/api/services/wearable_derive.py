"""Turns raw Samsung records (samsung_export) into what wearable_ingest stores: sleep sessions with stage minutes,
finished per-day values, workouts and body values. Deterministic arithmetic only.

Rules (design decisions 2, 5, 6, 7 and the controller's rulings):
- A night belongs to the local date of its end (each record's own time offset).
- Nights: naps (`sleep_type` 3) are set aside, then duplicates are dropped (longest first, a session overlapping a
  kept one by more than 50 % of its own length, e.g. the same night from another device). The rest are chained in
  start order: a session within 180 min of the current night's span joins it, whatever its local date (a night
  split across midnight or a change of time zone), unless the night would then run more than 18 h from its first
  start to its last end (a chain of daytime sleeps must not join two nights). The night's wake date is the local end date of the part that ends
  last; every part is stored with that wake date. Per wake date the longest night (union length) is the one used;
  its parts are `is_main = True`. Everything else is kept with `is_main = False` and never feeds nightly metrics.
- Nightly metrics come only from readings that start inside the union of the night's [start, end) windows. Days
  without a night get no nightly metrics; Samsung's day values (steps, distance, calories, stress) are taken for
  every day.
- Sleep minutes: over the union of the night's parts. Each part contributes its stages (or, without stages, its whole
  span), swept in start order so overlapping time counts once (the earlier-starting segment keeps it). Total = the
  non-awake minutes. Efficiency = the duration-weighted mean of the parts' efficiencies (Samsung's, else asleep /
  in-bed from that part's stages).
- Resting HR = the lowest time-weighted 30-minute mean of HR readings inside the night; a window counts only with at
  least 3 readings covering at least 20 minutes of it.
- Skin-temperature deviation = nightly mean minus Samsung's baseline on that night's rows when present; otherwise
  minus the median of the nightly means over the previous 30 days when at least 7 such nights exist; otherwise none.

Volume: bins (~726k in a real export) are sorted by start once and sliced per night with bisect.
"""
import bisect
import datetime as dt
import statistics
from collections import defaultdict
from collections.abc import Callable, Sequence
from operator import attrgetter

from services.samsung_export import Export, SleepRec, StageRec
from services.wearable_ingest import SleepIn, StageIn, WorkoutIn

NAP_TYPE = "3"
OVERLAP_SHARE = 0.5
BASELINE_DAYS = 30
BASELINE_MIN_NIGHTS = 7
MERGE_GAP_MIN = 180  # split night: parts this close are one night
MERGE_MAX_SPAN_H = 18  # ...unless joining would stretch the night (first start -> last end) past this
RESTING_WINDOW_MIN = 30
RESTING_MIN_READINGS = 3
RESTING_MIN_COVERED_MIN = 20

_start = attrgetter("start_utc")


def _minutes(a: dt.datetime, b: dt.datetime) -> float:
    return (b - a).total_seconds() / 60


def _overlap(a: SleepIn, b: SleepIn) -> float:
    return max(0.0, _minutes(max(a.start_utc, b.start_utc), min(a.end_utc, b.end_utc)))


# ---------------------------------------------------------------- sleep sessions

def derive_sleep(sleep: list[SleepRec], stages: list[StageRec]) -> tuple[list[SleepIn], dict[str, list[StageIn]]]:
    """Sessions with stage minutes and `is_main`, plus each session's stages keyed by its external id. Sessions that
    end at or before they start are dropped; stages whose session is absent are ignored."""
    valid = [r for r in sleep if r.end_utc > r.start_utc]
    known = {r.uuid for r in valid}
    by_session: dict[str, list[StageIn]] = defaultdict(list)
    for st in sorted(stages, key=lambda s: (s.start_utc, s.uuid)):
        if st.sleep_uuid in known and st.end_utc > st.start_utc:
            by_session[st.sleep_uuid].append(StageIn(st.uuid, st.start_utc, st.end_utc, st.stage))

    drafts: list[SleepIn] = []
    for r in valid:
        mins = defaultdict(float)
        for st in by_session.get(r.uuid, ()):
            mins[st.stage] += _minutes(st.start_utc, st.end_utc)
        drafts.append(SleepIn(
            external_id=r.uuid, start_utc=r.start_utc, end_utc=r.end_utc, tz_offset_min=r.tz_min,
            wake_date=r.wake_date, duration_min=float(round(_minutes(r.start_utc, r.end_utc))),
            deep_min=float(round(mins["deep"])), rem_min=float(round(mins["rem"])),
            light_min=float(round(mins["light"])), awake_min=float(round(mins["awake"])),
            efficiency=None if r.efficiency is None else round(r.efficiency, 1), sleep_type=r.sleep_type,
            is_main=False, device_id=r.device))

    main = _choose_main(drafts)
    sessions = [SleepIn(**{**s.__dict__, "is_main": s.external_id in main,
                           "wake_date": main.get(s.external_id, s.wake_date)}) for s in drafts]
    sessions.sort(key=lambda s: (s.start_utc, s.external_id))
    return sessions, dict(by_session)


def _choose_main(drafts: list[SleepIn]) -> dict[str, dt.date]:
    """{external id: the night's wake date} for every part of a night that is used (see the module rules)."""
    candidates = [s for s in drafts if s.sleep_type != NAP_TYPE]
    if not candidates:
        return {}
    longest = max(s.end_utc - s.start_utc for s in candidates)

    kept: list[SleepIn] = []  # sorted by start
    kept_starts: list[dt.datetime] = []
    for s in sorted(candidates, key=lambda s: (-(s.end_utc - s.start_utc), s.start_utc, s.external_id)):
        own = _minutes(s.start_utc, s.end_utc)
        k = bisect.bisect_left(kept_starts, s.end_utc) - 1  # kept sessions starting before s ends
        duplicate = False
        while k >= 0 and kept_starts[k] > s.start_utc - longest:
            if _overlap(s, kept[k]) > OVERLAP_SHARE * own:
                duplicate = True
                break
            k -= 1
        if not duplicate:
            at = bisect.bisect_left(kept_starts, s.start_utc)
            kept.insert(at, s)
            kept_starts.insert(at, s.start_utc)

    gap = dt.timedelta(minutes=MERGE_GAP_MIN)
    max_span = dt.timedelta(hours=MERGE_MAX_SPAN_H)
    nights: list[list[SleepIn]] = []
    lo: dt.datetime | None = None
    hi: dt.datetime | None = None
    for s in kept:
        if hi is not None and s.start_utc - hi <= gap and max(hi, s.end_utc) - lo <= max_span:
            nights[-1].append(s)
            hi = max(hi, s.end_utc)
        else:
            nights.append([s])
            lo, hi = s.start_utc, s.end_utc

    best: dict[dt.date, tuple[float, list[SleepIn]]] = {}
    for parts in nights:
        wake = max(parts, key=lambda p: (p.end_utc, p.external_id)).wake_date
        length = sum(_minutes(a, b) for a, b in _union([(p.start_utc, p.end_utc) for p in parts]))
        if wake not in best or length > best[wake][0]:  # nights are in start order: ties keep the earlier one
            best[wake] = (length, parts)
    return {p.external_id: wake for wake, (_, parts) in best.items() for p in parts}


# ---------------------------------------------------------------- daily values

class _Timeline:
    """Records sorted by start once; `within(a, b)` slices those starting in [a, b) by bisect."""

    def __init__(self, items: Sequence):
        self.items = sorted(items, key=_start)
        self.starts = [i.start_utc for i in self.items]

    def within(self, a: dt.datetime, b: dt.datetime) -> list:
        return self.items[bisect.bisect_left(self.starts, a):bisect.bisect_left(self.starts, b)]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _put(day: dict[str, float], field: str, value: float | None, ndigits: int) -> None:
    if value is not None:
        day[field] = float(round(value, ndigits))


def derive_days(export: Export, sessions: list[SleepIn]) -> dict[dt.date, dict[str, float]]:
    days: dict[dt.date, dict[str, float]] = defaultdict(dict)

    nights: dict[dt.date, list[SleepIn]] = defaultdict(list)
    for s in sessions:
        if s.is_main:
            nights[s.wake_date].append(s)

    hr, hrv, skin = _Timeline(export.hr), _Timeline(export.hrv), _Timeline(export.skin)
    resp, spo2 = _Timeline(export.resp), _Timeline(export.spo2)
    skin_nights: list[tuple[dt.date, float, float | None]] = []  # (wake date, nightly mean, Samsung baseline)

    part_ids = {s.external_id for parts in nights.values() for s in parts}
    stages: dict[str, list[StageRec]] = defaultdict(list)
    for st in export.stages:
        if st.sleep_uuid in part_ids and st.end_utc > st.start_utc:
            stages[st.sleep_uuid].append(st)

    for wake, parts in sorted(nights.items()):
        d = days[wake]
        _sleep_fields(d, parts, stages)
        spans = _union([(s.start_utc, s.end_utc) for s in parts])

        def within(timeline: _Timeline) -> list:
            return [x for a, b in spans for x in timeline.within(a, b)]

        _put(d, "resting_hr", _resting_hr(within(hr)), 0)
        bins = within(hrv)
        _put(d, "hrv_sdnn", _mean([x.value for x in bins]), 1)
        _put(d, "hrv_rmssd", _mean([x.value2 for x in bins if x.value2 is not None]), 1)
        _put(d, "respiratory_rate", _mean([x.value for x in within(resp)]), 1)
        readings = within(spo2)
        _put(d, "spo2_avg", _mean([x.spo2 for x in readings]), 1)
        _put(d, "spo2_min", min((x.min if x.min is not None else x.spo2 for x in readings), default=None), 1)
        temps = within(skin)
        if temps:
            mean = sum(x.value for x in temps) / len(temps)
            _put(d, "skin_temp_c", mean, 2)
            skin_nights.append((wake, mean, _mean([x.value2 for x in temps if x.value2 is not None])))

    _skin_deltas(days, skin_nights)

    for st in export.steps:
        d = days[st.local_date]
        d["steps"] = float(st.steps)
        _put(d, "distance_m", st.distance_m, 0)
        _put(d, "active_kcal", st.kcal, 0)

    stress: dict[dt.date, list[float]] = defaultdict(list)
    for r in export.stress:
        stress[r.local_date].append(r.score)
    for day, scores in stress.items():
        _put(days[day], "stress_avg", _mean(scores), 1)

    return {day: values for day, values in days.items() if values}


def _union(spans: list[tuple[dt.datetime, dt.datetime]]) -> list[tuple[dt.datetime, dt.datetime]]:
    """Overlapping spans merged, so no reading is counted twice."""
    out: list[tuple[dt.datetime, dt.datetime]] = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _sleep_fields(d: dict[str, float], parts: list[SleepIn], stages: dict[str, list[StageRec]]) -> None:
    """Minutes over the union of the night's parts: each part contributes its stages (or, without stages, its whole
    span as sleep), swept in start order so overlapping time is counted once; the earlier-starting segment keeps the
    overlap. Total = all non-awake minutes. Efficiency is the duration-weighted mean of the parts' efficiencies
    (Samsung's, else asleep / in-bed from that part's stages)."""
    segments: list[tuple[dt.datetime, dt.datetime, str]] = []
    staged_any = False
    eff_sum = eff_weight = 0.0
    for s in parts:
        own = stages.get(s.external_id)
        if own:
            staged_any = True
            segments += [(st.start_utc, st.end_utc, st.stage) for st in own]
        else:
            segments.append((s.start_utc, s.end_utc, "sleep"))
        staged = s.deep_min + s.rem_min + s.light_min + s.awake_min > 0
        eff = s.efficiency
        if eff is None and staged and s.duration_min > 0:
            eff = (s.deep_min + s.rem_min + s.light_min) / s.duration_min * 100
        if eff is not None and s.duration_min > 0:
            eff_sum += eff * s.duration_min
            eff_weight += s.duration_min

    mins: dict[str, float] = defaultdict(float)
    covered: dt.datetime | None = None
    for a, b, label in sorted(segments, key=lambda x: (x[0], x[1])):
        a = a if covered is None else max(a, covered)
        if b > a:
            mins[label] += _minutes(a, b)
        covered = b if covered is None else max(covered, b)

    d["sleep_total_min"] = float(round(sum(v for k, v in mins.items() if k != "awake")))
    if staged_any:
        d["sleep_deep_min"], d["sleep_rem_min"] = float(round(mins["deep"])), float(round(mins["rem"]))
        d["sleep_light_min"], d["sleep_awake_min"] = float(round(mins["light"])), float(round(mins["awake"]))
    _put(d, "sleep_efficiency", eff_sum / eff_weight if eff_weight else None, 1)


def _resting_hr(readings: list) -> float | None:
    """Lowest 30-minute mean of HR readings inside the night (design text). A window starts at each reading and
    holds the readings starting within the next 30 minutes; each is weighted by its own length clipped to the window
    (at least one second, so instantaneous readings count). A window counts only with RESTING_MIN_READINGS readings
    whose clipped lengths add up to RESTING_MIN_COVERED_MIN, so a short stretch at the end of the night or before a
    data gap cannot set the value.

    Running sums over the window; only readings that can reach past the window's end (those starting within the
    longest reading's length of it) are re-weighted, so ~1-minute bins cost O(n)."""
    if len(readings) < RESTING_MIN_READINGS:
        return None
    items = sorted(readings, key=_start)
    starts = [r.start_utc.timestamp() for r in items]
    ends = [r.end_utc.timestamp() for r in items]
    hrs = [r.hr for r in items]
    lengths = [max(e - s, 0.0) for s, e in zip(starts, ends)]
    weights = [max(x, 1.0) for x in lengths]
    longest = max(lengths)
    span, need = RESTING_WINDOW_MIN * 60.0, RESTING_MIN_COVERED_MIN * 60.0
    n, hi, num, den, cov = len(items), 0, 0.0, 0.0, 0.0
    best: float | None = None
    for i in range(n):
        window_end = starts[i] + span
        while hi < n and starts[hi] < window_end:
            num, den, cov = num + hrs[hi] * weights[hi], den + weights[hi], cov + lengths[hi]
            hi += 1
        if hi - i >= RESTING_MIN_READINGS:
            wn, wd, wc = num, den, cov
            k = hi - 1
            while k >= i and starts[k] > window_end - longest - 1:
                if ends[k] > window_end:
                    cut = weights[k] - max(window_end - starts[k], 1.0)
                    wn, wd = wn - hrs[k] * cut, wd - cut
                    wc -= ends[k] - window_end
                k -= 1
            if wc >= need - 1e-6:
                mean = wn / wd
                if best is None or mean < best:
                    best = mean
        num, den, cov = num - hrs[i] * weights[i], den - weights[i], cov - lengths[i]
    return best


def _skin_deltas(days: dict[dt.date, dict[str, float]], nights: list[tuple[dt.date, float, float | None]]) -> None:
    """Nights are in wake-date order. The previous-30-day window slides with two pointers."""
    lo = 0
    for i, (wake, mean, baseline) in enumerate(nights):
        if baseline is not None:
            _put(days[wake], "skin_temp_delta", mean - baseline, 2)
            continue
        first = wake - dt.timedelta(days=BASELINE_DAYS)
        while lo < i and nights[lo][0] < first:
            lo += 1
        window = [m for _, m, _ in nights[lo:i]]
        if len(window) >= BASELINE_MIN_NIGHTS:
            _put(days[wake], "skin_temp_delta", mean - statistics.median(window), 2)


# ---------------------------------------------------------------- body and workouts

def derive_body(export: Export) -> dict[dt.date, dict[str, float]]:
    """Body values per local day and kind: non-positive values dropped, the last weigh-in of the day wins."""
    best: dict[tuple[dt.date, str], tuple[dt.datetime, float]] = {}
    for r in export.body:
        if not r.value > 0:
            continue
        key = (r.local_date, r.kind)
        if key not in best or r.start_utc >= best[key][0]:
            best[key] = (r.start_utc, r.value)
    out: dict[dt.date, dict[str, float]] = defaultdict(dict)
    for (day, kind), (_, value) in sorted(best.items()):
        out[day][kind] = value
    return dict(out)


def _r0(value: float | None) -> float | None:
    return None if value is None else float(round(value))


def derive_workouts(export: Export) -> tuple[list[WorkoutIn], int]:
    """Workouts with their local date (from the start's offset). Rows ending before they start or with no positive
    duration are dropped and counted."""
    items: list[WorkoutIn] = []
    dropped = 0
    for w in export.workouts:
        if w.end_utc < w.start_utc or not w.duration_min > 0:
            dropped += 1
            continue
        items.append(WorkoutIn(
            external_id=w.uuid, start_utc=w.start_utc, end_utc=w.end_utc, tz_offset_min=w.tz_min,
            local_date=w.local_date, type_code=w.type_code, duration_min=float(round(w.duration_min)),
            kcal=_r0(w.kcal), distance_m=_r0(w.distance_m), hr_avg=_r0(w.hr_avg), hr_max=_r0(w.hr_max),
            device_id=w.device))
    return items, dropped
