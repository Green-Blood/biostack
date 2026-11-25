from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from db.database import get_session
from services import app_settings, clock, freshness
from services.i18n import Lang, get_lang, msg

router = APIRouter(prefix="/freshness", tags=["freshness"])


class IntervalIn(BaseModel):
    days: int | None = Field(default=None, ge=1, le=3650)


def _today(session: Session):
    return clock.today(app_settings.configured_zone(session))


@router.get("")
def read_freshness(session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> dict:
    today = _today(session)
    return {"today": today.isoformat(), "items": freshness.freshness_items(session, today, lang)}


@router.put("/{marker_key}/interval")
def set_interval(marker_key: str, body: IntervalIn, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> dict:
    today = _today(session)
    if not any(i["marker_key"] == marker_key for i in freshness.freshness_items(session, today, lang)):
        raise HTTPException(404, msg(lang, "http.marker_unknown"))
    freshness.set_override(session, marker_key, body.days)
    return next(i for i in freshness.freshness_items(session, today, lang) if i["marker_key"] == marker_key)
