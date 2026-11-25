import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from db.database import get_session
from services import signals
from services.i18n import Lang, get_lang, msg

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/overview")
def overview(session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    return signals.overview(session, lang)


@router.get("/series")
def series(keys: str = Query(...), from_: dt.date | None = Query(None, alias="from"), to: dt.date | None = None,
           session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    wanted = list(dict.fromkeys(k.strip() for k in keys.split(",") if k.strip()))
    for key in wanted:
        if key not in signals.METRICS:
            raise HTTPException(422, msg(lang, "http.signals_unknown_key", name=key))
    if not wanted:
        raise HTTPException(422, msg(lang, "http.signals_unknown_key", name=""))
    return signals.series(session, lang, wanted, from_, to)


@router.get("/sleep")
def sleep(from_: dt.date | None = Query(None, alias="from"), to: dt.date | None = None,
          session: Session = Depends(get_session)):
    return signals.sleep_list(session, from_, to)


@router.get("/sleep/{session_id}")
def sleep_detail(session_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    found = signals.sleep_detail(session, session_id)
    if found is None:
        raise HTTPException(404, msg(lang, "http.signals_night_not_found"))
    return found


@router.get("/workouts")
def workouts(from_: dt.date | None = Query(None, alias="from"), to: dt.date | None = None, type: int | None = None,
             session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    return signals.workouts(session, lang, from_, to, type)
