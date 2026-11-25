import datetime as dt
from collections.abc import Callable
from dataclasses import asdict, replace
from functools import partial

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from config import settings
from db.database import get_session
from db.models import CorrelationCache
from services import app_settings
from services.ai_provider import build_briefing_writer
from services.briefing import get_briefing
from services.briefing_writer import BriefingWriter
from services.correlation_phrases import describe
from services.correlation_store import AnalysisReport, load_correlations, load_report, recompute
from services.daily_series import variable_for
from services.early_warning import assess_risk
from services.graph_builder import build_graph, lag_label
from services.i18n import Lang, get_lang, msg, translate_text
from services.lag_analyzer import TargetReport

router = APIRouter(prefix="/analytics", tags=["analytics"])


class CorrelationOut(BaseModel):
    trigger: str
    trigger_label: str
    trigger_kind: str
    target: str
    target_label: str
    r: float
    spearman_r: float
    p_value: float
    spearman_p: float
    n_days: int
    lag_hours: int
    lag_label: str
    phrase: str
    effect: str


class CorrelationsOut(BaseModel):
    computed: bool
    computed_at: dt.datetime | None
    targets: list[TargetReport]
    correlations: list[CorrelationOut]


class FactorOut(BaseModel):
    key: str
    label: str
    weight: int
    points: float
    detail: str
    has_data: bool
    seen_in_days: int | None


class RiskOut(BaseModel):
    score: int | None
    level: str | None
    alert: bool
    reason: str
    factors: list[FactorOut]
    recommendations: list[str]


class BriefingOut(BaseModel):
    date: dt.date
    source: str
    label: str
    bullets: list[str]
    ai_enabled: bool
    can_retry: bool


def get_briefing_writer_factory() -> Callable[[], BriefingWriter]:
    return partial(build_briefing_writer, settings)


def _wording(c: CorrelationCache, lang: Lang) -> dict[str, str]:
    phrase, effect = describe(c.trigger_key, c.target_metric, c.correlation_score, c.lag_hours, lang)
    return {"phrase": phrase, "effect": effect}


def _correlations_out(session: Session, report: AnalysisReport | None, lang: Lang) -> CorrelationsOut:
    rows = [
        CorrelationOut(
            trigger=c.trigger_key, trigger_label=variable_for(c.trigger_key, lang).label, trigger_kind=variable_for(c.trigger_key).kind,
            target=c.target_metric, target_label=variable_for(c.target_metric, lang).label, r=c.correlation_score,
            spearman_r=c.spearman_score, p_value=c.p_value, spearman_p=c.spearman_p, n_days=c.n_days,
            lag_hours=c.lag_hours, lag_label=lag_label(c.lag_hours, lang), **_wording(c, lang),
        )
        for c in load_correlations(session)
    ]
    return CorrelationsOut(
        computed=report is not None, computed_at=report.computed_at if report else None,
        targets=[replace(t, reason=translate_text(lang, t.reason)) for t in report.targets] if report else [], correlations=rows,
    )


@router.post("/recompute")
def recompute_correlations(session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> CorrelationsOut:
    report = recompute(session)
    return _correlations_out(session, report, lang)


@router.get("/correlations")
def read_correlations(session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> CorrelationsOut:
    return _correlations_out(session, load_report(session), lang)


@router.get("/risk")
def read_risk(session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> RiskOut:
    risk = assess_risk(session, dt.datetime.now(dt.timezone.utc), app_settings.load_settings(session).bedtime,
                       app_settings.configured_zone(session), lang)
    return RiskOut(
        score=risk.score, level=risk.level, alert=risk.alert, reason=risk.reason,
        factors=[FactorOut(**asdict(f)) for f in risk.factors], recommendations=risk.recommendations,
    )


def _briefing_out(
    session: Session, writer_factory: Callable[[], BriefingWriter], lang: Lang, *, refresh: bool = False,
) -> BriefingOut:
    profile = app_settings.load_settings(session)
    briefing = get_briefing(
        session, dt.datetime.now(dt.timezone.utc), profile.bedtime, app_settings.configured_zone(session), writer_factory,
        ai_enabled=profile.ai_briefing, refresh=refresh, lang=lang,
    )
    return BriefingOut(date=briefing.day, source=briefing.source, label=briefing.label, bullets=briefing.bullets,
                       ai_enabled=profile.ai_briefing, can_retry=briefing.can_retry)


@router.get("/briefing")
def read_briefing(
    session: Session = Depends(get_session), writer_factory: Callable[[], BriefingWriter] = Depends(get_briefing_writer_factory),
    lang: Lang = Depends(get_lang),
) -> BriefingOut:
    return _briefing_out(session, writer_factory, lang)


@router.post("/briefing/refresh")
def refresh_briefing(
    session: Session = Depends(get_session), writer_factory: Callable[[], BriefingWriter] = Depends(get_briefing_writer_factory),
    lang: Lang = Depends(get_lang),
) -> BriefingOut:
    """Ask the AI again after a failed attempt. Needs the AI briefing setting; this is the only retry."""
    if not app_settings.load_settings(session).ai_briefing:
        raise HTTPException(409, msg(lang, "http.ai_off"))
    return _briefing_out(session, writer_factory, lang, refresh=True)


@router.get("/graph")
def read_graph(session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> dict:
    return build_graph(session, lang)
