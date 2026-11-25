"""Runs the lag analysis over everything logged and keeps the result: notable pairs in CorrelationCache, the
per-target status (including why data is insufficient) in the app settings."""
import datetime as dt

from pydantic import AwareDatetime, BaseModel
from sqlmodel import Session, delete, select

from db.models import AppSetting, CorrelationCache
from services import app_settings
from services.daily_series import build_predictors, build_targets
from services.lag_analyzer import TargetReport, analyze

REPORT_KEY = "analytics_report"


class AnalysisReport(BaseModel):
    computed_at: AwareDatetime
    targets: list[TargetReport]


def recompute(session: Session) -> AnalysisReport:
    bedtime = app_settings.load_settings(session).bedtime
    predictors, _ = build_predictors(session, bedtime, app_settings.configured_zone(session))
    result = analyze(build_targets(session), predictors)
    now = dt.datetime.now(dt.timezone.utc)
    session.exec(delete(CorrelationCache))
    session.add_all(
        CorrelationCache(
            target_metric=found.target, trigger_key=found.predictor, correlation_score=found.pearson_r,
            lag_hours=found.lag_hours, confidence_pct=round((1 - found.pearson_p) * 100, 1), p_value=found.pearson_p,
            spearman_score=found.spearman_r, spearman_p=found.spearman_p, n_days=found.n_days, last_updated=now,
        )
        for found in result.correlations
    )
    report = AnalysisReport(computed_at=now, targets=result.targets)
    session.merge(AppSetting(key=REPORT_KEY, value=report.model_dump(mode="json")))
    session.commit()
    return report


def load_correlations(session: Session) -> list[CorrelationCache]:
    return list(session.exec(select(CorrelationCache).order_by(CorrelationCache.confidence_pct.desc())))


def load_report(session: Session) -> AnalysisReport | None:
    row = session.get(AppSetting, REPORT_KEY)
    return AnalysisReport.model_validate(row.value) if row else None
