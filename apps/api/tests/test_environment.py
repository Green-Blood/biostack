import datetime as dt

import httpx
import pytest

from db.models import EnvironmentalLog
from main import app
from routers.environment import get_environment_client
from services.environment_client import EnvironmentReading, OpenMeteoClient, PressureReading
from services.environment_cron import LocationNotSet, pressure_delta_24h, refresh_environment
from services.scheduler import REFRESH_HOURS, build_scheduler

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def _reading(pressure=750.0, history=()):
    return EnvironmentReading(NOW, aqi=42, pm2_5=8.5, pm10=14.0, pressure_mmHg=pressure, humidity=61, pressure_history=tuple(history))


class FakeEnvironment:
    def __init__(self, reading: EnvironmentReading):
        self.reading, self.calls = reading, []

    def fetch(self, latitude: float, longitude: float) -> EnvironmentReading:
        self.calls.append((latitude, longitude))
        return self.reading


def test_delta_compares_with_the_reading_a_day_earlier():
    history = [PressureReading(NOW - dt.timedelta(hours=24), 755.0), PressureReading(NOW - dt.timedelta(hours=12), 752.0)]
    assert pressure_delta_24h(NOW, 750.0, history) == pytest.approx(-5.0)


def test_delta_accepts_a_reading_within_ninety_minutes_of_a_day_ago():
    assert pressure_delta_24h(NOW, 750.0, [PressureReading(NOW - dt.timedelta(hours=25), 752.0)]) == pytest.approx(-2.0)


def test_delta_is_none_without_history_near_a_day_ago():
    assert pressure_delta_24h(NOW, 750.0, []) is None
    assert pressure_delta_24h(NOW, 750.0, [PressureReading(NOW - dt.timedelta(hours=10), 752.0)]) is None
    assert pressure_delta_24h(NOW, None, [PressureReading(NOW - dt.timedelta(hours=24), 752.0)]) is None


def test_refresh_stores_a_log_with_the_delta(session):
    client = FakeEnvironment(_reading(history=[PressureReading(NOW - dt.timedelta(hours=24), 756.0)]))
    log = refresh_environment(session, client, 52.5, 13.4)
    assert client.calls == [(52.5, 13.4)]
    stored = session.get(EnvironmentalLog, log.id)
    assert (stored.pm2_5, stored.aqi, stored.humidity, stored.pressure_delta_24h) == (8.5, 42, 61, pytest.approx(-6.0))


def test_refresh_falls_back_to_earlier_stored_logs_for_the_delta(session):
    session.add(EnvironmentalLog(timestamp=NOW - dt.timedelta(hours=24), pressure_mmHg=753.0))
    session.commit()
    assert refresh_environment(session, FakeEnvironment(_reading()), 1, 2).pressure_delta_24h == pytest.approx(-3.0)


def test_refresh_survives_missing_history(session):
    assert refresh_environment(session, FakeEnvironment(_reading()), 1, 2).pressure_delta_24h is None


@pytest.fixture
def fake_environment(client):
    fake = FakeEnvironment(_reading(history=[PressureReading(NOW - dt.timedelta(hours=24), 755.0)]))
    app.dependency_overrides[get_environment_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_environment_client, None)


def test_refresh_endpoint_needs_a_location(client, fake_environment):
    res = client.post("/api/v1/environment/refresh")
    assert res.status_code == 409 and "location" in res.json()["detail"].lower() and fake_environment.calls == []


def test_refresh_endpoint_uses_the_saved_location(client, fake_environment):
    client.put("/api/v1/settings", json={"latitude": 52.5, "longitude": 13.4, "bedtime": "23:00"})
    res = client.post("/api/v1/environment/refresh")
    assert res.status_code == 201 and res.json()["pm2_5"] == 8.5 and res.json()["pressure_delta_24h"] == pytest.approx(-5.0)
    assert fake_environment.calls == [(52.5, 13.4)]
    latest = client.get("/api/v1/environment").json()
    assert [row["pm2_5"] for row in latest] == [8.5]


def test_refresh_reports_an_unreachable_service(client):
    class Down:
        def fetch(self, latitude, longitude):
            raise httpx.ConnectError("offline")

    app.dependency_overrides[get_environment_client] = lambda: Down()
    client.put("/api/v1/settings", json={"latitude": 1, "longitude": 2, "bedtime": "23:00"})
    res = client.post("/api/v1/environment/refresh")
    app.dependency_overrides.pop(get_environment_client, None)
    assert res.status_code == 502 and "Open-Meteo" in res.json()["detail"]


def test_location_not_set_is_a_distinct_error(session):
    with pytest.raises(LocationNotSet):
        refresh_environment(session, FakeEnvironment(_reading()), None, None)


AIR = {"current": {"time": "2026-11-10T12:00", "pm10": 14.0, "pm2_5": 8.5, "us_aqi": 42}}
WEATHER = {
    "current": {"time": "2026-11-10T12:00", "surface_pressure": 1000.0, "relative_humidity_2m": 61},
    "hourly": {"time": ["2026-11-09T12:00", "2026-11-10T12:00", "2026-11-10T13:00"], "surface_pressure": [1010.0, 1000.0, None]},
}


def _open_meteo(handler=None) -> tuple[OpenMeteoClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=AIR if "air-quality" in request.url.host else WEATHER)

    return OpenMeteoClient(httpx.Client(transport=httpx.MockTransport(handler or respond))), seen


def test_open_meteo_client_reads_both_services():
    client, seen = _open_meteo()
    reading = client.fetch(52.5, 13.4)
    assert (reading.timestamp, reading.aqi, reading.pm2_5, reading.pm10, reading.humidity) == (NOW, 42, 8.5, 14.0, 61)
    assert reading.pressure_mmHg == pytest.approx(750.06, abs=0.01)
    assert [(p.timestamp, round(p.pressure_mmHg, 1)) for p in reading.pressure_history] == [
        (NOW - dt.timedelta(hours=24), 757.6), (NOW, 750.1)]
    air = next(r for r in seen if "air-quality" in r.url.host)
    assert air.url.params["current"] == "pm10,pm2_5,us_aqi" and air.url.params["latitude"] == "52.5"
    weather = next(r for r in seen if "air-quality" not in r.url.host)
    assert weather.url.params["current"] == "surface_pressure,relative_humidity_2m" and weather.url.params["past_days"] == "2"


def test_open_meteo_error_status_raises():
    client, _ = _open_meteo(lambda request: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        client.fetch(1, 2)


def test_scheduler_runs_the_job_every_three_hours_and_is_not_started():
    scheduler = build_scheduler(lambda: None)
    (job,) = scheduler.get_jobs()
    assert REFRESH_HOURS == 3 and job.trigger.interval == dt.timedelta(hours=3)
    assert not scheduler.running


def test_app_starts_the_scheduler_only_when_enabled(monkeypatch):
    from fastapi.testclient import TestClient

    from config import settings
    import main

    started = []
    monkeypatch.setattr(main, "start_scheduler", lambda: started.append(1) or None)
    with TestClient(main.app):
        pass
    assert started == []
    monkeypatch.setattr(settings, "enable_scheduler", True)
    with TestClient(main.app):
        pass
    assert started == [1]
