from collections.abc import Callable
from functools import partial

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from config import settings
from db.database import get_session
from services import app_settings, clock, insights
from services.ai_provider import AiNotConfigured, build_insight_client
from services.gemini_client import AiRequestError, GeminiClient
from services.gemini_parser import ParseError
from services.i18n import Lang, get_lang

router = APIRouter(prefix="/insights", tags=["insights"])


def get_insight_client_factory() -> Callable[[], GeminiClient]:
    return partial(build_insight_client, settings)


def _guard(call):
    """The AI answers only when the owner turned the AI summary on; failures become messages the page can show."""
    try:
        return call()
    except AiNotConfigured as exc:
        raise HTTPException(409, str(exc)) from exc
    except (AiRequestError, ParseError) as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/system/{system}")
def system_guide(system: str, refresh: bool = False, session: Session = Depends(get_session), lang: Lang = Depends(get_lang),
                 factory: Callable[[], GeminiClient] = Depends(get_insight_client_factory)) -> dict:
    if not app_settings.load_settings(session).ai_briefing:
        return {"ai_enabled": False}
    guide = _guard(lambda: insights.system_guide(session, system, lang, factory(), refresh))
    if guide is None:
        raise HTTPException(404, "No results in this panel yet.")
    return {"ai_enabled": True, **guide}


@router.get("/marker/{key}")
def marker_guide(key: str, refresh: bool = False, session: Session = Depends(get_session), lang: Lang = Depends(get_lang),
                 factory: Callable[[], GeminiClient] = Depends(get_insight_client_factory)) -> dict:
    if not app_settings.load_settings(session).ai_briefing:
        return {"ai_enabled": False}
    guide = _guard(lambda: insights.marker_guide(session, key, lang, factory(), refresh))
    if guide is None:
        raise HTTPException(404, "No numeric result for this marker yet.")
    return {"ai_enabled": True, **guide}


@router.get("/overview")
def overview(refresh: bool = False, session: Session = Depends(get_session), lang: Lang = Depends(get_lang),
             factory: Callable[[], GeminiClient] = Depends(get_insight_client_factory)) -> dict:
    enabled = app_settings.load_settings(session).ai_briefing
    today = clock.today(app_settings.configured_zone(session))
    return {"ai_enabled": enabled, **_guard(lambda: insights.overview(session, lang, factory() if enabled else None, today, refresh))}
