import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from db.database import get_session
from db.models import Medication
from services import app_settings, clock
from services.courses import course_effect, course_out, known_marker
from services.i18n import Lang, get_lang, msg

router = APIRouter(prefix="/courses", tags=["courses"])
IMPORTED_EDITABLE = {"target_marker_key", "notes"}


class CourseIn(BaseModel):
    name: str
    dosage: str = ""
    start_date: dt.date
    days: int | None = Field(default=None, ge=1, le=3650)
    end_date: dt.date | None = None
    target_marker_key: str | None = None
    notes: str = ""


class CoursePatch(BaseModel):
    name: str | None = None
    dosage: str | None = None
    start_date: dt.date | None = None
    days: int | None = Field(default=None, ge=1, le=3650)
    end_date: dt.date | None = None
    target_marker_key: str | None = None
    notes: str | None = None


def _today(session: Session) -> dt.date:
    return clock.today(app_settings.configured_zone(session))


def _get(session: Session, course_id: int, lang: str) -> Medication:
    course = session.get(Medication, course_id)
    if course is None:
        raise HTTPException(404, msg(lang, "http.course_not_found"))
    return course


def _check(session: Session, name: str | None, key: str | None, lang: str) -> None:
    if name is not None and not name.strip():
        raise HTTPException(422, msg(lang, "http.course_name_required"))
    if key and not known_marker(key, session):
        raise HTTPException(422, msg(lang, "http.course_marker_unknown"))


def _end(start: dt.date, days: int | None, end: dt.date | None, lang: str) -> dt.date | None:
    if days is not None and end is not None:
        raise HTTPException(422, msg(lang, "http.course_days_and_end"))
    if days is not None:
        return start + dt.timedelta(days=days - 1)
    if end is not None and end < start:
        raise HTTPException(422, msg(lang, "http.course_bad_dates"))
    return end


@router.get("")
def list_courses(session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> list[dict]:
    today = _today(session)
    courses = session.exec(select(Medication)).all()
    courses.sort(key=lambda c: (c.start_date or dt.date.min, c.id or 0), reverse=True)
    return [course_out(session, c, today, lang) for c in courses]


@router.post("", status_code=201)
def create_course(body: CourseIn, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> dict:
    _check(session, body.name, body.target_marker_key, lang)
    end = _end(body.start_date, body.days, body.end_date, lang)
    course = Medication(name=body.name.strip(), dosage=body.dosage, start_date=body.start_date, end_date=end,
                        target_marker_key=body.target_marker_key or None, notes=body.notes, source="manual")
    session.add(course)
    session.commit()
    session.refresh(course)
    return course_out(session, course, _today(session), lang)


@router.patch("/{course_id}")
def update_course(course_id: int, body: CoursePatch, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> dict:
    course = _get(session, course_id, lang)
    fields = body.model_dump(exclude_unset=True)
    if course.source != "manual" and not set(fields) <= IMPORTED_EDITABLE:
        raise HTTPException(403, msg(lang, "http.course_forbidden"))
    _check(session, fields.get("name"), fields.get("target_marker_key"), lang)
    if "name" in fields and fields["name"] is None:
        raise HTTPException(422, msg(lang, "http.course_name_required"))
    start = fields.get("start_date") or course.start_date
    if "days" in fields or "end_date" in fields:
        if start is None:
            raise HTTPException(422, msg(lang, "http.course_no_start"))
        course.end_date = _end(start, fields.get("days"), fields.get("end_date"), lang)
    elif start and course.end_date and course.end_date < start:
        raise HTTPException(422, msg(lang, "http.course_bad_dates"))
    for name in ("name", "dosage", "start_date", "notes"):
        if name in fields and fields[name] is not None:
            setattr(course, name, fields[name].strip() if name == "name" else fields[name])
    if "target_marker_key" in fields:
        course.target_marker_key = fields["target_marker_key"] or None
    session.add(course)
    session.commit()
    session.refresh(course)
    return course_out(session, course, _today(session), lang)


@router.delete("/{course_id}", status_code=204)
def delete_course(course_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> None:
    course = _get(session, course_id, lang)
    if course.source != "manual":
        raise HTTPException(403, msg(lang, "http.course_forbidden"))
    session.delete(course)
    session.commit()


@router.get("/{course_id}/effect")
def effect(course_id: int, marker: str | None = None, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> dict:
    course = _get(session, course_id, lang)
    key = marker or course.target_marker_key
    if not key:
        raise HTTPException(422, msg(lang, "http.effect_no_marker"))
    if not known_marker(key, session):
        raise HTTPException(404, msg(lang, "http.marker_unknown"))
    if course.start_date is None:
        raise HTTPException(422, msg(lang, "http.course_no_start"))
    return course_effect(session, course, key, lang)
