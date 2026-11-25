from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from db.database import get_session
from services import search as search_service
from services.i18n import Lang, get_lang

router = APIRouter(tags=["search"])


@router.get("/search")
def search(q: str = Query("", max_length=200), limit: int = Query(6, ge=1, le=50),
           session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> dict:
    """Local, read-only search over markers, records, files, medications, journal and imaging. The query string is redacted from the access log (see services/log_redaction)."""
    return search_service.search(session, q, lang, limit)
