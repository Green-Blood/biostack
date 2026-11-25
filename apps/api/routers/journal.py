import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from db.database import get_session
from db.models import HealthJournal
from services.i18n import Lang, get_lang, msg

router = APIRouter(prefix="/journal", tags=["journal"])

JournalCategory = Literal["symptom", "doctor_visit", "note"]


def _clean_title(value: str) -> str:
    if not value.strip():
        raise ValueError("Give the entry a title.")
    return value.strip()


class EntryIn(BaseModel):
    entry_date: dt.date = Field(default_factory=dt.date.today)
    category: JournalCategory = "note"
    title: str
    description: str = ""
    severity_1_10: int | None = Field(default=None, ge=1, le=10)
    body_location: str | None = None

    _title = field_validator("title")(_clean_title)


class EntryPatch(BaseModel):
    entry_date: dt.date | None = None
    category: JournalCategory | None = None
    title: str | None = None
    description: str | None = None
    severity_1_10: int | None = Field(default=None, ge=1, le=10)
    body_location: str | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return None if value is None else _clean_title(value)


class EntryOut(BaseModel):
    id: int
    entry_date: dt.date
    category: str
    title: str
    description: str
    severity_1_10: int | None
    body_location: str | None


def _get_entry(session: Session, entry_id: int, lang: Lang) -> HealthJournal:
    entry = session.get(HealthJournal, entry_id)
    if entry is None:
        raise HTTPException(404, msg(lang, "http.journal_not_found"))
    return entry


@router.post("", status_code=201)
def create_entry(body: EntryIn, session: Session = Depends(get_session)) -> EntryOut:
    entry = HealthJournal(**body.model_dump())
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return EntryOut.model_validate(entry, from_attributes=True)


@router.get("")
def list_entries(
    session: Session = Depends(get_session), category: JournalCategory | None = None,
    from_: dt.date | None = Query(None, alias="from"), to: dt.date | None = None,
) -> list[EntryOut]:
    query = select(HealthJournal).order_by(HealthJournal.entry_date.desc(), HealthJournal.id.desc())
    if category:
        query = query.where(HealthJournal.category == category)
    if from_:
        query = query.where(HealthJournal.entry_date >= from_)
    if to:
        query = query.where(HealthJournal.entry_date <= to)
    return [EntryOut.model_validate(e, from_attributes=True) for e in session.exec(query)]


@router.patch("/{entry_id}")
def update_entry(entry_id: int, body: EntryPatch, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> EntryOut:
    entry = _get_entry(session, entry_id, lang)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return EntryOut.model_validate(entry, from_attributes=True)


@router.delete("/{entry_id}", status_code=204)
def delete_entry(entry_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> Response:
    session.delete(_get_entry(session, entry_id, lang))
    session.commit()
    return Response(status_code=204)
