from collections.abc import Callable
from dataclasses import asdict
from functools import partial

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from config import settings
from db.database import get_session
from db.models import RecordOrgan, ScanMeasurement
from routers.records import get_or_404
from services import scan_store
from services.ai_provider import AiNotConfigured, build_scan_extractor
from services.gemini_client import AiRequestError
from services.gemini_parser import ParseError
from services.i18n import Lang, get_lang, msg, translate_text
from services.organs import organ_name, param_name
from services.scan_extractor import ScanExtractor
from services.scan_store import MeasurementIn

router = APIRouter(tags=["scans"])


def get_scan_extractor_factory() -> Callable[[], ScanExtractor]:
    return partial(build_scan_extractor, settings)


class ScanIn(BaseModel):
    organs: list[str] = []
    measurements: list[MeasurementIn] = []


def _out(session: Session, record_id: int, lang: str) -> dict:
    organs = session.exec(select(RecordOrgan).where(RecordOrgan.record_id == record_id).order_by(RecordOrgan.organ_key)).all()
    rows = session.exec(select(ScanMeasurement).where(ScanMeasurement.record_id == record_id)
                        .order_by(ScanMeasurement.organ_key, ScanMeasurement.param_key, ScanMeasurement.side)).all()
    return {
        "record_id": record_id,
        "organs": [{"organ_key": o.organ_key, "name": organ_name(o.organ_key, lang), "origin": o.origin} for o in organs],
        "measurements": [{"organ_key": m.organ_key, "param_key": m.param_key, "name": param_name(m.param_key, lang),
                          "side": m.side, "value": m.value, "value_text": m.value_text, "unit": m.unit,
                          "origin": m.origin, "verified": m.verified} for m in rows],
    }


@router.get("/scans/{record_id}")
def get_scan(record_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    get_or_404(session, record_id, lang)
    return _out(session, record_id, lang)


@router.put("/scans/{record_id}")
def put_scan(record_id: int, body: ScanIn, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    get_or_404(session, record_id, lang)
    try:
        scan_store.replace_review(session, record_id, body.organs, body.measurements)
    except scan_store.ScanInvalid as exc:
        session.rollback()
        raise HTTPException(422, msg(lang, exc.key))
    return _out(session, record_id, lang)


@router.post("/scans/{record_id}/extract")
def extract_scan(record_id: int, ai: bool = False, session: Session = Depends(get_session),
                 lang: Lang = Depends(get_lang),
                 extractor_factory: Callable[[], ScanExtractor] = Depends(get_scan_extractor_factory)):
    """Rule-based reading; with ?ai=1 the AI then fills what the rules left (opt-in, never automatic)."""
    get_or_404(session, record_id, lang)
    extractor = None
    if ai:  # built before the rule step, so "AI not configured" writes nothing
        try:
            extractor = extractor_factory()
        except AiNotConfigured as exc:
            raise HTTPException(503, translate_text(lang, str(exc))) from exc
    report = scan_store.run_rule_extraction(session, record_id)
    ai_report = None
    if extractor is not None:
        hint = msg(lang, "hint.scan_by_hand")
        try:
            ai_report = scan_store.run_ai_extraction(session, record_id, extractor)
        except ParseError as exc:
            raise HTTPException(502, msg(lang, "http.scan_unreadable", hint=hint)) from exc
        except AiRequestError as exc:
            raise HTTPException(502, msg(lang, "http.ai_retry", error=translate_text(lang, str(exc)), hint=hint)) from exc
    return {"report": asdict(report), "ai_report": asdict(ai_report) if ai_report else None,
            **_out(session, record_id, lang)}
