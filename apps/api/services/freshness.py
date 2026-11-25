"""How old each marker's latest result is, against a re-test interval (a rule of thumb, never medical advice).

An interval is the owner's own override (AppSetting "retest_days:<marker>") or the catalog default. A finished
course whose target marker has no newer result forces the marker to at least "due".
"""
import datetime as dt

from sqlmodel import Session, select

from db.models import DEMO_SOURCE, AppSetting, Biomarker, Medication
from services.markers import marker_display_name, marker_retest_days, marker_system
from services.queries import biomarker_rows

OVERRIDE_PREFIX = "retest_days:"
DUE_FACTOR = 1.5
_RANK = {"fresh": 0, "due": 1, "overdue": 2}


def load_overrides(session: Session) -> dict[str, int]:
    out = {}
    for row in session.exec(select(AppSetting).where(AppSetting.key.startswith(OVERRIDE_PREFIX))):
        days = row.value.get("days") if isinstance(row.value, dict) else None
        if isinstance(days, int):
            out[row.key[len(OVERRIDE_PREFIX):]] = days
    return out


def set_override(session: Session, marker_key: str, days: int | None) -> None:
    key = OVERRIDE_PREFIX + marker_key
    row = session.get(AppSetting, key)
    if days is None:
        if row:
            session.delete(row)
    else:
        session.merge(AppSetting(key=key, value={"days": days}))
    session.commit()


def interval_for(marker_key: str, overrides: dict[str, int]) -> tuple[int | None, str]:
    if marker_key in overrides:
        return overrides[marker_key], "custom"
    return marker_retest_days(marker_key), "default"


def status_for(age_days: int, retest_days: int | None) -> str:
    if retest_days is None or age_days <= retest_days:
        return "fresh"
    return "due" if age_days <= DUE_FACTOR * retest_days else "overdue"


def numeric_rows(session: Session) -> list[tuple[Biomarker, dt.date]]:
    """Numeric results, oldest first, demo rows left out once any real result exists."""
    rows = [(b, d) for b, d, _ in biomarker_rows(session) if b.value is not None]
    if any(b.source != DEMO_SOURCE for b, _ in rows):
        rows = [(b, d) for b, d in rows if b.source != DEMO_SOURCE]
    return rows


def freshness_items(session: Session, today: dt.date, lang: str = "en") -> list[dict]:
    latest: dict[str, tuple[Biomarker, dt.date]] = {}
    for b, d in numeric_rows(session):
        latest[b.marker_key] = (b, d)
    overrides = load_overrides(session)
    pending = _pending_courses(session, today, {k: v[1] for k, v in latest.items()})
    items = []
    for key, (bm, date) in latest.items():
        retest, source = interval_for(key, overrides)
        age = max((today - date).days, 0)
        status, reason, course_id = status_for(age, retest), "interval", None
        if key in pending:
            course_id = pending[key]
            reason = "course"
            if _RANK[status] < _RANK["due"]:
                status = "due"
        items.append({
            "marker_key": key, "display_name": marker_display_name(key, bm.display_name, lang), "system": marker_system(key),
            "last_date": date.isoformat(), "age_days": age, "retest_days": retest, "interval_source": source,
            "status": status, "due_in_days": None if retest is None else retest - age, "reason": reason, "course_id": course_id,
        })
    order = {"overdue": 0, "due": 1, "fresh": 2}
    items.sort(key=lambda i: (order[i["status"]], i["due_in_days"] if i["due_in_days"] is not None else 10**9, i["display_name"].lower()))
    return items


def _pending_courses(session: Session, today: dt.date, last_dates: dict[str, dt.date]) -> dict[str, int]:
    """marker_key -> id of the latest finished course that has no later result for its target marker."""
    found: dict[str, tuple[dt.date, int]] = {}
    for course in session.exec(select(Medication).where(Medication.target_marker_key.is_not(None))):
        key = course.target_marker_key
        if course.end_date is None or course.end_date >= today or key not in last_dates:
            continue
        if last_dates[key] >= course.end_date:  # a result on the end day counts as after, as in course_effect
            continue
        if key not in found or course.end_date > found[key][0]:
            found[key] = (course.end_date, course.id)
    return {k: v[1] for k, v in found.items()}

