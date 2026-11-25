"""Stores one environment reading and the 24-hour pressure change (falling pressure is a common headache trigger)."""
import datetime as dt
from collections.abc import Iterable

from sqlmodel import Session, select

from db.database import engine
from db.models import EnvironmentalLog
from services import app_settings
from services.environment_client import EnvironmentClient, OpenMeteoClient, PressureReading
from services.half_life_engine import as_utc

DELTA_TOLERANCE = dt.timedelta(minutes=90)


class LocationNotSet(Exception):
    """Environment readings need a latitude and longitude in Settings."""


def pressure_delta_24h(now: dt.datetime, pressure: float | None, history: Iterable[PressureReading]) -> float | None:
    """Pressure now minus the reading closest to 24 hours ago (within 90 minutes); None when there is none."""
    if pressure is None:
        return None
    target = as_utc(now) - dt.timedelta(hours=24)
    nearest = min(history, key=lambda r: abs(as_utc(r.timestamp) - target), default=None)
    if nearest is None or abs(as_utc(nearest.timestamp) - target) > DELTA_TOLERANCE:
        return None
    return pressure - nearest.pressure_mmHg


def refresh_environment(session: Session, client: EnvironmentClient, latitude: float | None, longitude: float | None) -> EnvironmentalLog:
    if latitude is None or longitude is None:
        raise LocationNotSet("Set your location in Settings first.")
    reading = client.fetch(latitude, longitude)
    stored = [
        PressureReading(log.timestamp, log.pressure_mmHg)
        for log in session.exec(select(EnvironmentalLog).where(EnvironmentalLog.pressure_mmHg.is_not(None)))
    ]
    log = EnvironmentalLog(
        timestamp=reading.timestamp, aqi=reading.aqi, pm2_5=reading.pm2_5, pm10=reading.pm10,
        pressure_mmHg=reading.pressure_mmHg, humidity=reading.humidity,
        pressure_delta_24h=pressure_delta_24h(reading.timestamp, reading.pressure_mmHg, [*reading.pressure_history, *stored]),
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


def run_scheduled_refresh() -> None:
    """Scheduler entry point; a missing location or a network failure just skips this round."""
    with Session(engine) as session:
        location = app_settings.load_settings(session)
        try:
            refresh_environment(session, OpenMeteoClient(), location.latitude, location.longitude)
        except Exception:  # noqa: BLE001 - a background job must never take the app down
            session.rollback()
