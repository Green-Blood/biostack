"""Body signals read model: overview tiles, series, sleep nights, workouts.

Every read loads its rows with a fixed number of queries and does the arithmetic (bands, averages, grouping) here in
Python, so the cost does not grow with the number of nights or workouts. Nights come from DailyMetric (the night's
totals, merged once); the stored SleepSession parts are only used for start/end and stages, because the stage minutes
of merged parts can overlap each other."""
import datetime as dt
from collections import defaultdict

from sqlalchemy import func, or_
from sqlmodel import Session, select

from db.models import DEMO_SOURCE, BodyMeasurement, DailyMetric, ImportJob, SleepSession, SleepStage, Workout
from services import app_settings, clock
from services.i18n import msg

# metric key -> unit code (msg key `signals.unit.<code>`; "" = no unit). The whitelist for /series is these keys.
METRICS: dict[str, str] = {
    "sleep_total_min": "min", "sleep_deep_min": "min", "sleep_rem_min": "min", "sleep_light_min": "min",
    "sleep_awake_min": "min", "sleep_efficiency": "percent",
    "resting_hr": "bpm", "hrv_sdnn": "ms", "hrv_rmssd": "ms", "stress_avg": "",
    "skin_temp_delta": "celsius", "skin_temp_c": "celsius", "spo2_avg": "percent", "spo2_min": "percent",
    "respiratory_rate": "brpm", "vo2_max": "vo2", "steps": "steps", "distance_m": "m", "active_kcal": "kcal",
    "weight": "kg",
}
TILE_KEYS = ("sleep_total_min", "resting_hr", "hrv_sdnn", "skin_temp_delta", "spo2_avg", "steps", "weight")
DEFAULT_SPAN_DAYS = 90
FRESH_DAYS = 7
SPARK_DAYS = 30
BAND_DAYS = 30
BAND_MIN_POINTS = 10
STALE_AFTER_DAYS = 7  # watch data older than this is "up to {date}": windows anchor on that date, not on today
IMPORT_KIND = "samsung_health"
# Day totals that grow through the day: the newest day of a snapshot (or today) is only part of a day.
PARTIAL_KEYS = ("steps", "distance_m", "active_kcal")

# Names for the codes present in the owner's export, from Samsung Health's published exercise-type list
# ("Predefined Exercise Type", Samsung Health Data SDK): https://developer.samsung.com/health/android/data/api-reference/EXERCISE_TYPE.html
# Names are the list's own wording; RU/EN texts live in services/i18n_messages.py as `signals.workout.<code>`.
WORKOUT_CODES = (0, 1001, 1002, 10007, 11007, 15002, 15003, 15005)

_DAILY_FIELDS = tuple(k for k in METRICS if k != "weight")
_TILE_DAILY = tuple(k for k in TILE_KEYS if k != "weight")


def metric_name(lang: str, key: str) -> str:
    return msg(lang, f"signals.metric.{key}")


def metric_unit(lang: str, key: str) -> str:
    code = METRICS[key]
    return msg(lang, f"signals.unit.{code}") if code else ""


def workout_name(lang: str, code: int) -> str:
    if code in WORKOUT_CODES:
        return msg(lang, f"signals.workout.{code}")
    return msg(lang, "signals.workout_unknown", code=code)


# ---- band ----

def _percentile(sorted_values: list[float], q: float) -> float:
    pos = (len(sorted_values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def band(values: list[float]) -> dict | None:
    """25th-75th percentile of the given values; None with fewer than 10 points."""
    if len(values) < BAND_MIN_POINTS:
        return None
    ordered = sorted(values)
    return {"p25": round(_percentile(ordered, 0.25), 2), "p75": round(_percentile(ordered, 0.75), 2)}


def position(value: float | None, b: dict | None) -> str | None:
    if value is None or b is None:
        return None
    return "below" if value < b["p25"] else "above" if value > b["p75"] else "within"


def band_before(points: dict[dt.date, float], day: dt.date) -> dict | None:
    """The band for `day`: the previous 30 days, not including `day` itself."""
    lo = day - dt.timedelta(days=BAND_DAYS)
    return band([v for d, v in points.items() if lo <= d < day])


# ---- loading ----

def _today(session: Session) -> dt.date:
    return clock.today(app_settings.configured_zone(session))


def as_of(session: Session) -> dt.date | None:
    """The latest date the watch data reaches: the newest main night's wake date or the newest day holding a tile
    value, whichever is later. Demo rows and demo-owned fields do not count."""
    wake = session.exec(select(func.max(SleepSession.wake_date)).where(SleepSession.is_main,
                                                                        SleepSession.source != DEMO_SOURCE)).one()
    rows = session.exec(select(DailyMetric).where(DailyMetric.source != DEMO_SOURCE,
                                                  or_(*(getattr(DailyMetric, k).is_not(None) for k in _TILE_DAILY)))
                        .order_by(DailyMetric.metric_date.desc()))
    day = next((r.metric_date for r in rows
                if any(getattr(r, k) is not None and (r.field_sources or {}).get(k) != DEMO_SOURCE for k in _TILE_DAILY)),
               None)
    found = [d for d in (wake, day) if d is not None]
    return max(found) if found else None


def freshness(session: Session) -> dict:
    """`today` in the configured zone, `as_of`, `stale` (as_of more than 7 days back) and `anchor`: the day the
    "recent" windows end on (as_of when stale, else today)."""
    today = _today(session)
    last = as_of(session)
    stale = last is not None and (today - last).days > STALE_AFTER_DAYS
    return {"today": today, "as_of": last, "stale": stale, "anchor": last if stale else today}


def _fresh_json(f: dict) -> dict:
    return {"today": f["today"].isoformat(), "as_of": f["as_of"].isoformat() if f["as_of"] else None, "stale": f["stale"]}


def _newest_days(session: Session, keys) -> dict[str, dt.date | None]:
    """The newest real (non-demo) day per day-total key (one query per key, a fixed number)."""
    return {k: session.exec(select(func.max(DailyMetric.metric_date)).where(getattr(DailyMetric, k).is_not(None),
                                                                         DailyMetric.source != DEMO_SOURCE)).one()
            for k in keys if k in PARTIAL_KEYS}


def is_partial(key: str, day: dt.date | None, newest: dict[str, dt.date | None], f: dict) -> bool:
    """The snapshot's newest day of a day total is cut off when the data is stale (the export was taken mid-day) or
    when that day is today."""
    return (key in PARTIAL_KEYS and day is not None and day == newest.get(key)
            and (f["stale"] or day == f["today"]))


def utc_iso(value: dt.datetime | None) -> str | None:
    """A stored UTC time as ISO 8601 with an explicit +00:00 (SQLite may hand it back without a zone)."""
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=dt.UTC)).astimezone(dt.UTC).isoformat()


def _daily_points(session: Session, lo: dt.date, hi: dt.date, keys) -> dict[str, dict[dt.date, float]]:
    rows = session.exec(select(DailyMetric).where(DailyMetric.metric_date >= lo, DailyMetric.metric_date <= hi)).all()
    out: dict[str, dict[dt.date, float]] = {}
    for key in keys:
        if key == "weight":
            continue
        out[key] = {r.metric_date: float(v) for r in sorted(rows, key=lambda r: r.metric_date)
                    if (v := getattr(r, key)) is not None}
    return out


def _weight_points(session: Session, lo: dt.date, hi: dt.date) -> dict[dt.date, float]:
    rows = session.exec(select(BodyMeasurement).where(BodyMeasurement.kind == "weight", BodyMeasurement.measured_on >= lo,
                                                      BodyMeasurement.measured_on <= hi).order_by(BodyMeasurement.measured_on)).all()
    return {r.measured_on: r.value for r in rows}


def load_points(session: Session, keys, lo: dt.date, hi: dt.date) -> dict[str, dict[dt.date, float]]:
    """One DailyMetric query (plus one for weight) for all keys."""
    out = _daily_points(session, lo, hi, keys)
    if "weight" in keys:
        out["weight"] = _weight_points(session, lo, hi)
    return out


def _local(utc: dt.datetime, offset_min: int) -> str:
    return (utc + dt.timedelta(minutes=offset_min)).replace(tzinfo=None).isoformat(timespec="seconds")


def _num(v: float | None) -> float | None:
    return None if v is None else round(v, 1)


# ---- overview ----

def overview(session: Session, lang: str) -> dict:
    """Tiles: the latest value in the 7 days up to the anchor (today, or the data's last day when it is stale), its
    band and a 30-day spark ending on the anchor. Weight measured after a stale anchor still shows; watch values after
    it (only demo rows can be there) do not."""
    f = freshness(session)
    today, anchor = f["today"], f["anchor"]
    spark_lo = anchor - dt.timedelta(days=SPARK_DAYS - 1)
    lo = spark_lo - dt.timedelta(days=FRESH_DAYS + BAND_DAYS)
    points = _daily_points(session, lo, anchor, TILE_KEYS)  # watch values end on the anchor
    points["weight"] = _weight_points(session, lo, max(today, anchor))  # a weigh-in after old watch data still counts
    fresh_lo = anchor - dt.timedelta(days=FRESH_DAYS - 1)
    newest = _newest_days(session, TILE_KEYS)
    tiles = []
    for key in TILE_KEYS:
        pts = points[key]
        recent = [d for d in pts if d >= fresh_lo]
        day = max(recent) if recent else None
        value = pts[day] if day else None
        b = band_before(pts, day) if day else None
        partial = is_partial(key, day, newest, f)
        tiles.append({"key": key, "name": metric_name(lang, key), "unit": metric_unit(lang, key),
                      "value": value, "date": day.isoformat() if day else None,
                      "spark": [{"date": d.isoformat(), "value": v} for d, v in sorted(pts.items()) if d >= spark_lo],
                      "band": b, "position": None if partial else position(value, b), "partial": partial})
    last_night = _last_night(session)
    has_data = (last_night is not None or f["as_of"] is not None
                or session.exec(select(DailyMetric.metric_date).where(DailyMetric.source != DEMO_SOURCE).limit(1)).first() is not None
                or session.exec(select(Workout.id).where(Workout.source != DEMO_SOURCE).limit(1)).first() is not None
                or session.exec(select(BodyMeasurement.id).where(BodyMeasurement.kind == "weight",
                                                                 BodyMeasurement.source != DEMO_SOURCE).limit(1)).first() is not None)
    job = session.exec(select(ImportJob).where(ImportJob.kind == IMPORT_KIND, ImportJob.status == "done")
                       .order_by(ImportJob.finished_at.desc(), ImportJob.id.desc())).first()
    latest = {"finished_at": utc_iso(job.finished_at), "summary": job.summary or {}} if job else None
    sleep = points["sleep_total_min"]
    latest_sleep = max((d for d in sleep if d <= today), default=None)
    short_sleep = (latest_sleep is not None and (today - latest_sleep).days <= 1
                   and all(0 < sleep.get(latest_sleep - dt.timedelta(days=i), 0) < 420 for i in range(2)))
    return {"tiles": tiles, "last_night": last_night, "has_data": has_data, "latest_import": latest,
            "short_sleep_end": latest_sleep.isoformat() if short_sleep else None, **_fresh_json(f)}


def _last_night(session: Session) -> dict | None:
    wake = session.exec(select(SleepSession.wake_date).where(SleepSession.is_main, SleepSession.source != DEMO_SOURCE)
                        .order_by(SleepSession.wake_date.desc()).limit(1)).first()
    if wake is None:
        return None
    parts = session.exec(select(SleepSession).where(SleepSession.wake_date == wake, SleepSession.is_main)).all()
    n = _night(parts, session.get(DailyMetric, wake))
    return {"session_id": n["session_id"], "wake_date": n["wake_date"], "start_local": n["start_local"],
            "end_local": n["end_local"], "duration_min": n["duration_min"],
            "stages": {k: n[k] for k in ("deep", "rem", "light", "awake")}}


# ---- sleep ----

def _night(parts: list[SleepSession], daily: DailyMetric | None) -> dict:
    """One night: start = earliest part start, end = latest part end, minutes from the DailyMetric night totals
    (parts' own minutes can overlap), falling back to the parts' sums when the night has no daily row."""
    first = min(parts, key=lambda p: (p.start_utc, p.id))
    last = max(parts, key=lambda p: (p.end_utc, p.id))

    def pick(column: str, attr: str) -> float | None:
        v = getattr(daily, column, None) if daily else None
        return v if v is not None else sum(getattr(p, attr) for p in parts)

    eff = getattr(daily, "sleep_efficiency", None) if daily else None
    if eff is None and len(parts) == 1:
        eff = parts[0].efficiency
    return {"session_id": first.id, "wake_date": first.wake_date.isoformat(),
            "start_local": _local(first.start_utc, first.tz_offset_min), "end_local": _local(last.end_utc, last.tz_offset_min),
            "duration_min": pick("sleep_total_min", "duration_min"), "deep": pick("sleep_deep_min", "deep_min"),
            "rem": pick("sleep_rem_min", "rem_min"), "light": pick("sleep_light_min", "light_min"),
            "awake": pick("sleep_awake_min", "awake_min"), "efficiency": eff, "parts": len(parts)}


_SUMMARY = {"duration_min": "sleep_total_min", "deep": "sleep_deep_min", "rem": "sleep_rem_min", "light": "sleep_light_min",
            "awake": "sleep_awake_min", "efficiency": "sleep_efficiency"}


def _window_summary(rows: list[DailyMetric]) -> dict:
    out: dict = {"nights": sum(1 for r in rows if r.sleep_total_min is not None)}
    for name, col in _SUMMARY.items():
        vals = [getattr(r, col) for r in rows if getattr(r, col) is not None]
        out[name] = round(sum(vals) / len(vals), 1) if vals else None
    return out


def sleep_list(session: Session, lo: dt.date | None, hi: dt.date | None) -> dict:
    """Nights in [lo, hi] (default: the 90 days to today) and the last-30 / previous-30 summary, anchored on the
    data's last day when it is stale."""
    f = freshness(session)
    anchor = f["anchor"]
    hi = hi or f["today"]
    lo = lo or hi - dt.timedelta(days=DEFAULT_SPAN_DAYS - 1)
    parts = session.exec(select(SleepSession).where(SleepSession.is_main, SleepSession.wake_date >= lo,
                                                    SleepSession.wake_date <= hi)).all()
    daily = {r.metric_date: r for r in session.exec(select(DailyMetric).where(
        DailyMetric.metric_date >= lo, DailyMetric.metric_date <= hi)).all()}
    by_date: dict[dt.date, list[SleepSession]] = defaultdict(list)
    for p in parts:
        by_date[p.wake_date].append(p)
    nights = [_night(ps, daily.get(d)) for d, ps in sorted(by_date.items(), reverse=True)]

    rows = session.exec(select(DailyMetric).where(DailyMetric.metric_date >= anchor - dt.timedelta(days=2 * 30 - 1),
                                                  DailyMetric.metric_date <= anchor)).all()
    split = anchor - dt.timedelta(days=29)
    last30 = _window_summary([r for r in rows if r.metric_date >= split])
    prev30 = _window_summary([r for r in rows if r.metric_date < split])
    change = {k: (round(last30[k] - prev30[k], 1) if last30[k] is not None and prev30[k] is not None else None)
              for k in _SUMMARY}
    return {"nights": nights, "summary": {"last30": last30, "prev30": prev30, "change": change}, **_fresh_json(f)}


def sleep_detail(session: Session, session_id: int) -> dict | None:
    part = session.get(SleepSession, session_id)
    if part is None:
        return None
    parts = (session.exec(select(SleepSession).where(SleepSession.wake_date == part.wake_date, SleepSession.is_main)).all()
             if part.is_main else [part])
    stages = session.exec(select(SleepStage).where(SleepStage.session_id.in_([p.id for p in parts]))
                          .order_by(SleepStage.start_utc, SleepStage.id)).all()
    offsets = {p.id: p.tz_offset_min for p in parts}
    night = _night(parts, session.get(DailyMetric, part.wake_date) if part.is_main else None)
    night["is_main"] = part.is_main
    return {"session": night,
            "stages": [{"start_local": _local(s.start_utc, offsets[s.session_id]),
                        "end_local": _local(s.end_utc, offsets[s.session_id]), "stage": s.stage} for s in stages]}


# ---- series ----

def series(session: Session, lang: str, keys: list[str], lo: dt.date | None, hi: dt.date | None) -> dict:
    """Points in [lo, hi] (default: the 90 days to today). The band and position belong to the last shown point; a
    partial day (see is_partial) gets no position."""
    f = freshness(session)
    hi = hi or f["today"]
    lo = lo or hi - dt.timedelta(days=DEFAULT_SPAN_DAYS - 1)
    # Old data: watch values end on as_of (anything later is only demo rows); weight keeps its own dates.
    points = _daily_points(session, lo - dt.timedelta(days=BAND_DAYS), min(hi, f["anchor"]) if f["stale"] else hi, keys)
    if "weight" in keys:
        points["weight"] = _weight_points(session, lo - dt.timedelta(days=BAND_DAYS), hi)
    newest = _newest_days(session, keys)
    out = {}
    for key in keys:
        shown = {d: v for d, v in points[key].items() if lo <= d <= hi}
        last = max(shown) if shown else None
        b = band_before(points[key], last) if last else None
        partial = is_partial(key, last, newest, f)
        out[key] = {"name": metric_name(lang, key), "unit": metric_unit(lang, key),
                    "points": [{"date": d.isoformat(), "value": v} for d, v in sorted(shown.items())],
                    "band": b, "position": position(shown[last], b) if last and not partial else None, "partial": partial}
    return {"series": out, **_fresh_json(f)}


# ---- workouts ----

def workouts(session: Session, lang: str, lo: dt.date | None, hi: dt.date | None, type_code: int | None) -> dict:
    hi = hi or _today(session)
    lo = lo or hi - dt.timedelta(days=DEFAULT_SPAN_DAYS - 1)
    rows = session.exec(select(Workout).where(Workout.local_date >= lo, Workout.local_date <= hi)
                        .order_by(Workout.start_utc.desc(), Workout.id.desc())).all()
    counts: dict[int, int] = defaultdict(int)
    for w in rows:
        counts[w.type_code] += 1
    items = [{"id": w.id, "local_date": w.local_date.isoformat(), "start_local": _local(w.start_utc, w.tz_offset_min),
              "type_code": w.type_code, "type_name": workout_name(lang, w.type_code), "duration_min": w.duration_min,
              "kcal": w.kcal, "distance_m": w.distance_m, "hr_avg": w.hr_avg, "hr_max": w.hr_max}
             for w in rows if type_code is None or w.type_code == type_code]
    types = [{"type_code": c, "type_name": workout_name(lang, c), "count": n}
             for c, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    return {"items": items, "types": types}
