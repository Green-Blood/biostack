import datetime as dt

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from db.database import get_session
from db.models import EnvironmentalLog
from services import app_settings
from services.environment_client import EnvironmentClient, OpenMeteoClient
from services.environment_cron import LocationNotSet, refresh_environment
from services.half_life_engine import as_utc
from services.i18n import Lang, get_lang, msg, translate_text

router = APIRouter(prefix="/environment", tags=["environment"])


class EnvironmentOut(BaseModel):
    id: int
    timestamp: dt.datetime
    aqi: float | None
    pm2_5: float | None
    pm10: float | None
    pressure_mmHg: float | None
    pressure_delta_24h: float | None
    humidity: float | None

    @classmethod
    def of(cls, log: EnvironmentalLog) -> "EnvironmentOut":
        return cls(**log.model_dump(exclude={"timestamp"}), timestamp=as_utc(log.timestamp))


def get_environment_client() -> EnvironmentClient:
    return OpenMeteoClient()


@router.post("/refresh", status_code=201)
def refresh(session: Session = Depends(get_session), client: EnvironmentClient = Depends(get_environment_client),
            lang: Lang = Depends(get_lang)) -> EnvironmentOut:
    location = app_settings.load_settings(session)
    try:
        return EnvironmentOut.of(refresh_environment(session, client, location.latitude, location.longitude))
    except LocationNotSet as error:
        raise HTTPException(409, translate_text(lang, str(error))) from error
    except httpx.HTTPError as error:
        raise HTTPException(502, msg(lang, "http.open_meteo")) from error


@router.get("")
def recent(limit: int = Query(24, ge=1, le=500), session: Session = Depends(get_session)) -> list[EnvironmentOut]:
    logs = session.exec(select(EnvironmentalLog).order_by(EnvironmentalLog.timestamp.desc()).limit(limit))
    return [EnvironmentOut.of(log) for log in logs]
