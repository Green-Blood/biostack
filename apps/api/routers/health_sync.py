"""Wearable webhook. Phones and automations send an X-API-Key header, not the browser bearer token."""
import datetime as dt
import secrets

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, status
from sqlmodel import Session, select

from config import settings
from db.database import get_session
from db.models import DailyMetric
from services import profile as profile_svc
from services.health_payload import NoMetricsError, PayloadError, is_hc_webhook, parse_body, parse_payload
from services.metrics_store import store_hc_records, upsert_daily_metrics


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_secret_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing X-API-Key")


webhook = APIRouter(prefix="/api/v1", tags=["health-sync"], dependencies=[Depends(require_api_key)])
metrics = APIRouter(tags=["metrics"])


@webhook.post("/health-sync")
def health_sync(payload: object = Body(...), session: Session = Depends(get_session)) -> dict:
    body = parse_body(payload)
    daily_error: str | None = None
    if is_hc_webhook(payload):
        days = store_hc_records(session, payload)  # an empty batch (the app's test send) is fine, not a 422
    else:
        try:
            days = parse_payload(payload)
        except PayloadError as error:
            if not body:
                raise HTTPException(422, str(error)) from error
            days = {}
            if not isinstance(error, NoMetricsError):
                daily_error = str(error)  # a real problem with the daily metrics, not just "this is a body-only payload"
    upsert_daily_metrics(session, days, source="health_sync")
    values = {(day, kind): v for day, kinds in body.items() for kind, v in kinds.items()}
    manual = profile_svc.manual_keys(session, set(values))  # a hand-entered value is never replaced by a sync
    profile_svc.upsert_measurements(session, {k: v for k, v in values.items() if k not in manual}, "sync")
    dates = set(days) | set(body)
    answer: dict = {"days": len(dates), "dates": sorted(day.isoformat() for day in dates)}
    if body:
        answer["body"] = {day.isoformat(): kinds for day, kinds in sorted(body.items())} | {"skipped_manual": len(manual)}
    if daily_error:
        answer["daily_metrics_error"] = daily_error
    return answer


@metrics.get("/metrics")
def list_metrics(days: int = Query(30, ge=1, le=3650), session: Session = Depends(get_session)) -> list[DailyMetric]:
    since = dt.date.today() - dt.timedelta(days=days)
    return list(session.exec(select(DailyMetric).where(DailyMetric.metric_date >= since).order_by(DailyMetric.metric_date.desc())))
