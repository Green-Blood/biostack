"""Courses (a supplement or medicine taken over a period) and the before/after comparison around one.

A course is a Medication row. The comparison only sets two results side by side; it never claims a cause and never
advises a dose.
"""
import datetime as dt

from sqlmodel import Session

from db.models import Medication
from services.freshness import interval_for, load_overrides, numeric_rows
from services.i18n import msg
from services.markers import _catalog, marker_display_name, units_compatible
from services.tiers import latest_tiers, tiers_for_unit
from services.trends import Point, compute_deltas

OPEN_COURSE_RETEST_DAYS = 28  # re-test wait for an open-ended course whose marker has no interval
BASELINE_INTERVALS = 2  # a baseline older than this many re-test intervals no longer counts


def known_marker(marker_key: str, session: Session) -> bool:
    return marker_key in _catalog() or any(b.marker_key == marker_key for b, _ in numeric_rows(session))


def course_status(course: Medication, today: dt.date) -> str:
    if course.start_date is None and course.end_date is None:
        return "undated"  # nothing says when it was taken, so it must not pass as running
    if course.start_date and course.start_date > today:
        return "planned"
    if course.end_date and course.end_date < today:
        return "finished"
    return "active"


def marker_name(session: Session, marker_key: str | None, lang: str) -> str | None:
    if not marker_key:
        return None
    stored = next((b.display_name for b, _ in reversed(numeric_rows(session)) if b.marker_key == marker_key), None)
    return marker_display_name(marker_key, stored or _catalog().get(marker_key, {}).get("display_name", marker_key), lang)


def course_out(session: Session, course: Medication, today: dt.date, lang: str) -> dict:
    status = course_status(course, today)
    start, end = course.start_date, course.end_date
    return {
        "id": course.id, "name": course.name, "dosage": course.dosage,
        "start_date": start.isoformat() if start else None, "end_date": end.isoformat() if end else None,
        "days": (end - start).days + 1 if start and end else None, "status": status,
        "ends_in_days": (end - today).days if end and status != "finished" else None,
        "target_marker_key": course.target_marker_key, "target_marker_name": marker_name(session, course.target_marker_key, lang),
        "notes": course.notes, "source": course.source, "editable": course.source == "manual",
    }


def _range_for(row, tiers: list[dict]) -> tuple[float | None, float | None]:
    if row.ref_min is not None or row.ref_max is not None:
        return row.ref_min, row.ref_max
    normal = next((t for t in tiers_for_unit(tiers, row.unit) if t["tier"] == "normal"), None)
    return (normal["min"], normal["max"]) if normal else (None, None)


def _point(found) -> dict | None:
    return {"date": found[1].isoformat(), "value": found[0].value, "unit": found[0].unit} if found else None


def course_effect(session: Session, course: Medication, marker_key: str, lang: str) -> dict:
    start, end = course.start_date, course.end_date
    rows = [(b, d) for b, d in numeric_rows(session) if b.marker_key == marker_key]
    retest, _ = interval_for(marker_key, load_overrides(session))
    before = next(((b, d) for b, d in reversed(rows) if d <= start), None)
    if before and retest is not None and (start - before[1]).days > BASELINE_INTERVALS * retest:
        before = None
    wait = retest or OPEN_COURSE_RETEST_DAYS
    earliest = start + dt.timedelta(days=wait)  # an open-ended course has no end: wait one re-test interval
    after = next(((b, d) for b, d in rows if d > start and (d >= end if end else d >= earliest)), None)
    tiers = latest_tiers(session).get(marker_key, [])
    anchor = (after or before or (None, None))[0]
    out = {
        "course_id": course.id, "marker_key": marker_key,
        "display_name": marker_name(session, marker_key, lang), "unit": anchor.unit if anchor else "",
        "before": _point(before), "after": _point(after),
        "delta_abs": None, "delta_pct": None, "toward_range": None, "stayed_in_range": None, "days_between": None,
        "state": "measured", "retest_due_date": None, "note": msg(lang, "effect.note"),
    }
    if after is None:
        due = max(end or start, earliest if end is None or retest else start)
        out.update(state="waiting_for_retest", retest_due_date=due.isoformat())
    elif before is None:
        out["state"] = "no_baseline"
    elif not units_compatible(before[0].unit, after[0].unit):
        out.update(state="unit_mismatch", note=msg(lang, "effect.unit_mismatch"))
    else:
        (b, bd), (a, ad) = before, after
        lo, hi = _range_for(a, tiers)
        blo, bhi = _range_for(b, tiers)
        delta = compute_deltas([Point(bd.isoformat(), b.value, blo, bhi), Point(ad.isoformat(), a.value, lo, hi)])[0]
        out.update(delta_abs=delta.abs, delta_pct=delta.pct, toward_range=delta.toward_range,
                   stayed_in_range=delta.stayed_in_range, days_between=(ad - bd).days)
    return out
