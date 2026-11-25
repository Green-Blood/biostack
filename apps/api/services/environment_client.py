"""Air quality and weather from Open-Meteo (no API key). Sits behind a Protocol so tests use a fake.

Air quality: https://air-quality-api.open-meteo.com/v1/air-quality  (current: pm10, pm2_5, us_aqi)
Weather:     https://api.open-meteo.com/v1/forecast                  (current: surface_pressure, relative_humidity_2m;
             hourly surface_pressure over past_days gives the reading from 24 hours ago). Pressure arrives in hPa.
"""
import datetime as dt
from dataclasses import dataclass
from typing import Protocol

import httpx

AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
MMHG_PER_HPA = 0.750062
TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class PressureReading:
    timestamp: dt.datetime
    pressure_mmHg: float


@dataclass(frozen=True)
class EnvironmentReading:
    timestamp: dt.datetime
    aqi: float | None
    pm2_5: float | None
    pm10: float | None
    pressure_mmHg: float | None
    humidity: float | None
    pressure_history: tuple[PressureReading, ...] = ()


class EnvironmentClient(Protocol):
    def fetch(self, latitude: float, longitude: float) -> EnvironmentReading: ...


def _utc(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text).replace(tzinfo=dt.timezone.utc)


def _mmhg(hectopascal: float | None) -> float | None:
    return None if hectopascal is None else hectopascal * MMHG_PER_HPA


class OpenMeteoClient:
    def __init__(self, http: httpx.Client | None = None) -> None:
        self._http = http or httpx.Client(timeout=TIMEOUT_SECONDS)

    def _get(self, url: str, params: dict) -> dict:
        response = self._http.get(url, params={**params, "timezone": "UTC"})
        response.raise_for_status()
        return response.json()

    def fetch(self, latitude: float, longitude: float) -> EnvironmentReading:
        place = {"latitude": latitude, "longitude": longitude}
        air = self._get(AIR_URL, {**place, "current": "pm10,pm2_5,us_aqi"})["current"]
        weather = self._get(WEATHER_URL, {
            **place, "current": "surface_pressure,relative_humidity_2m", "hourly": "surface_pressure",
            "past_days": 2, "forecast_days": 1,
        })
        now = _utc(weather["current"]["time"])
        hourly = weather["hourly"]
        history = tuple(
            PressureReading(_utc(stamp), _mmhg(value))
            for stamp, value in zip(hourly["time"], hourly["surface_pressure"])
            if value is not None and _utc(stamp) <= now
        )
        return EnvironmentReading(
            timestamp=now, aqi=air.get("us_aqi"), pm2_5=air.get("pm2_5"), pm10=air.get("pm10"),
            pressure_mmHg=_mmhg(weather["current"].get("surface_pressure")),
            humidity=weather["current"].get("relative_humidity_2m"), pressure_history=history,
        )
