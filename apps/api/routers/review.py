import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from db.database import get_session
from db.models import AppSetting, Biomarker, DateReview, MarkerAlias
from services.i18n import Lang, get_lang, msg
from services.markers import catalog_markers
from services.queries import biomarker_rows

router = APIRouter(prefix="/review", tags=["review"])


class AliasIn(BaseModel):
    raw_name: str
    marker_key: str
    display_name: str


class IgnoreIn(BaseModel):
    raw_name: str


IGNORED_KEY = "unmapped_ignored"


def _ignored(session: Session) -> list[str]:
    row = session.get(AppSetting, IGNORED_KEY)
    return list(row.value) if row and isinstance(row.value, list) else []


class DateIn(BaseModel):
    record_id: int
    confirmed_date: dt.date


@router.get("/unmapped")
def unmapped(session: Session = Depends(get_session)):
    hidden = {n.casefold() for n in _ignored(session)}
    items: dict[str, dict] = {}
    for b, date, _ in biomarker_rows(session):  # oldest first, so the last numeric row is the latest
        if not b.marker_key.startswith("unmapped:") or b.raw_name.strip().casefold() in hidden:
            continue
        item = items.setdefault(b.raw_name, {"raw_name": b.raw_name, "count": 0, "latest_value": None,
                                             "latest_date": date.isoformat(), "unit": ""})
        item["count"] += 1
        if b.value is not None:
            item.update(latest_value=b.value, latest_date=date.isoformat(), unit=b.unit)
        elif item["latest_value"] is None:
            item["latest_date"] = date.isoformat()
    return [items[k] for k in sorted(items)]


@router.post("/ignore", status_code=204)
def ignore(body: IgnoreIn, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    """Hide a printed name from the unmapped list. Nothing is deleted; the results stay as they are."""
    name = body.raw_name.strip()
    if not name:
        raise HTTPException(422, msg(lang, "http.review_name_required"))
    names = _ignored(session)
    if name.casefold() not in {n.casefold() for n in names}:
        session.merge(AppSetting(key=IGNORED_KEY, value=[*names, name]))
        session.commit()
    return Response(status_code=204)


@router.post("/alias")
def set_alias(body: AliasIn, session: Session = Depends(get_session)):
    # a catalog marker always keeps its own canonical (English) name, whatever name the client sent
    canonical = {m["marker_key"]: m["display_name"] for m in catalog_markers("en")}
    if body.marker_key in canonical:
        body.display_name = canonical[body.marker_key]
    alias = session.exec(select(MarkerAlias).where(MarkerAlias.raw_name == body.raw_name)).first()
    if alias is None:
        alias = MarkerAlias(raw_name=body.raw_name, marker_key=body.marker_key,
                            display_name=body.display_name)
    alias.marker_key, alias.display_name = body.marker_key, body.display_name
    session.add(alias)
    updated = 0
    for b in session.exec(select(Biomarker).where(Biomarker.raw_name == body.raw_name)):
        b.marker_key, b.display_name = body.marker_key, body.display_name
        updated += 1
    session.commit()
    return {"updated": updated}


@router.post("/date")
def confirm_date(body: DateIn, session: Session = Depends(get_session)):
    review = session.get(DateReview, body.record_id) or DateReview(record_id=body.record_id)
    review.confirmed_date = body.confirmed_date
    session.add(review)
    session.commit()
    return {"ok": True}
