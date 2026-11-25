import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from config import settings
from db.database import get_session
from db.models import DailyMetric
from main import app
from services.health_payload import PayloadError, hc_day_totals, hc_records, parse_payload

URL = "/api/v1/health-sync"
KEY = {"X-API-Key": settings.api_secret_key}
DAY = dt.date(2026, 11, 10)

AUTO_EXPORT = {"data": {"metrics": [
    {"name": "resting_heart_rate", "units": "count/min", "data": [{"date": "2026-11-10 00:00:00 +0100", "qty": 54}]},
    {"name": "heart_rate_variability", "units": "ms", "data": [{"date": "2026-11-10 03:00:00 +0100", "qty": 40}, {"date": "2026-11-10 05:00:00 +0100", "qty": 50}]},
    {"name": "step_count", "units": "count", "data": [{"date": "2026-11-10 00:00:00 +0100", "qty": 3000}, {"date": "2026-11-10 12:00:00 +0100", "qty": 4500}]},
    {"name": "vo2_max", "units": "ml/(kg·min)", "data": [{"date": "2026-11-10 00:00:00 +0100", "qty": 44.5}]},
    {"name": "sleep_analysis", "units": "hr", "data": [{"date": "2026-11-10 00:00:00 +0100", "totalSleep": 7.5, "deep": 1.25, "rem": 1.5}]},
    {"name": "something_unknown", "data": [{"date": "2026-11-10 00:00:00 +0100", "qty": 1}]},
]}}


def test_auto_export_shape_is_parsed_per_day():
    assert parse_payload(AUTO_EXPORT) == {DAY: {
        "resting_hr": 54, "hrv_sdnn": 45, "steps": 7500, "vo2_max": 44.5,
        "sleep_total_min": 450, "sleep_deep_min": 75, "sleep_rem_min": 90,
    }}


def test_auto_export_days_are_kept_apart():
    payload = {"data": {"metrics": [{"name": "step_count", "data": [
        {"date": "2026-11-09 10:00:00 +0100", "qty": 100}, {"date": "2026-11-10 10:00:00 +0100", "qty": 200}]}]}}
    assert parse_payload(payload) == {dt.date(2026, 11, 9): {"steps": 100}, DAY: {"steps": 200}}


def test_flat_shape_is_parsed():
    assert parse_payload({"date": "2026-11-10", "hrv_sdnn": 48, "steps": 8000}) == {DAY: {"hrv_sdnn": 48, "steps": 8000}}


@pytest.mark.parametrize("payload", [
    {}, {"date": "2026-11-10"}, {"hrv_sdnn": 48}, {"date": "not a date", "steps": 1},
    {"date": "2026-11-10", "steps": "lots"}, {"data": {"metrics": []}}, {"data": {"metrics": [{"name": "unknown", "data": []}]}},
    {"data": {"metrics": "nope"}}, [],
])
def test_unusable_payloads_are_rejected(payload):
    with pytest.raises(PayloadError):
        parse_payload(payload)


@pytest.fixture
def anonymous(engine):
    """A client without the bearer header: the webhook authenticates with X-API-Key instead."""
    def _session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_missing_or_wrong_key_is_unauthorized(anonymous):
    flat = {"date": "2026-11-10", "steps": 1}
    assert anonymous.post(URL, json=flat).status_code == 401
    assert anonymous.post(URL, json=flat, headers={"X-API-Key": "wrong"}).status_code == 401


def test_webhook_stores_a_day(anonymous, session):
    res = anonymous.post(URL, json=AUTO_EXPORT, headers=KEY)
    assert res.status_code == 200 and res.json() == {"days": 1, "dates": ["2026-11-10"]}
    row = session.get(DailyMetric, DAY)
    assert (row.hrv_sdnn, row.steps, row.sleep_total_min, row.source) == (45, 7500, 450, "health_sync")


def test_partial_update_keeps_the_other_fields(anonymous, session):
    anonymous.post(URL, json={"date": "2026-11-10", "hrv_sdnn": 48, "steps": 8000}, headers=KEY)
    anonymous.post(URL, json={"date": "2026-11-10", "resting_hr": 52}, headers=KEY)
    session.expire_all()
    row = session.get(DailyMetric, DAY)
    assert (row.hrv_sdnn, row.steps, row.resting_hr) == (48, 8000, 52)


def test_bad_payload_is_422_with_a_reason(anonymous):
    res = anonymous.post(URL, json={"date": "2026-11-10"}, headers=KEY)
    assert res.status_code == 422 and "metric" in res.json()["detail"]


def test_metrics_are_listed_for_the_token_holder(client, anonymous):
    anonymous.post(URL, json={"date": "2026-11-10", "steps": 8000}, headers=KEY)
    rows = client.get("/api/v1/metrics", params={"days": 30}).json()
    assert [(r["metric_date"], r["steps"]) for r in rows] == [("2026-11-10", 8000)]


def test_a_real_sync_replaces_a_demo_day_entirely(anonymous, session):
    session.add(DailyMetric(metric_date=DAY, hrv_sdnn=80.0, steps=9000, source="demo"))
    session.commit()
    anonymous.post(URL, json={"date": "2026-11-10", "resting_hr": 52}, headers=KEY)
    session.expire_all()
    row = session.get(DailyMetric, DAY)
    assert (row.resting_hr, row.hrv_sdnn, row.steps, row.source) == (52, None, None, "health_sync")


def _meta(record_id: str, origin: str = "com.sec.android.app.shealth") -> dict:
    return {"id": record_id, "data_origin": origin}


HC_WEBHOOK = {
    "timestamp": "2026-11-10T21:00:00+01:00", "app_version": "1.0", "timezone": "Europe/Berlin",
    "steps": [{"count": 3000, "start_time": "2026-11-10T08:00:00+01:00", "end_time": "2026-11-10T09:00:00+01:00", "metadata": _meta("s1")},
              {"count": 4500, "start_time": "2026-11-10T12:00:00+01:00", "end_time": "2026-11-10T13:00:00+01:00", "metadata": _meta("s2")}],
    "resting_heart_rate": [{"bpm": 54, "time": "2026-11-10T07:00:00+01:00", "metadata": _meta("r1")}],
    "heart_rate_variability": [{"rmssd_millis": 40, "time": "2026-11-10T03:00:00+01:00", "metadata": _meta("h1")},
                               {"rmssd_millis": 50, "time": "2026-11-10T05:00:00+01:00", "metadata": _meta("h2")}],
    "skin_temperature": [{"delta_celsius": 0.4, "time": "2026-11-10T04:00:00+01:00", "metadata": _meta("t1")}],
    "sleep": [{"session_end_time": "2026-11-10T07:00:00+01:00", "duration_seconds": 28800, "metadata": _meta("n1"), "stages": [
        {"stage": "4", "duration_seconds": 14400}, {"stage": "5", "duration_seconds": 4500},
        {"stage": "6", "duration_seconds": 5400}, {"stage": "1", "duration_seconds": 1800}]}],
    "weight": [{"kilograms": 81.2, "time": "2026-11-10T07:30:00+01:00", "metadata": _meta("w1")}],
    "body_fat": [{"percentage": 19.5, "time": "2026-11-10T07:30:00+01:00", "metadata": _meta("f1")}],
}
HC_DAY = {"steps": 7500, "resting_hr": 54, "hrv_sdnn": 45, "skin_temp_delta": 0.4,
          "sleep_total_min": 405, "sleep_deep_min": 75, "sleep_rem_min": 90}


def _batch(**lists) -> dict:
    return {"timestamp": "2026-11-10T22:00:00+01:00", "app_version": "1.0", **lists}


def _day(session) -> tuple:
    session.expire_all()
    row = session.get(DailyMetric, DAY)
    return row.steps, row.sleep_total_min, row.resting_hr


def test_hc_webhook_records_make_the_day():
    records = hc_records(HC_WEBHOOK)
    assert {r.day for r in records} == {DAY}
    assert hc_day_totals(records) == HC_DAY


def test_hc_webhook_same_night_from_two_apps_counts_once():
    other = _batch(sleep=[{"session_end_time": "2026-11-10T07:05:00+01:00", "duration_seconds": 20000, "metadata": _meta("x1", "com.google.android.apps.fitness")}])
    assert hc_day_totals(hc_records(HC_WEBHOOK) + hc_records(other))["sleep_total_min"] == 405


def test_hc_webhook_resend_edit_and_delete_never_double_count(anonymous, session):
    res = anonymous.post(URL, json=HC_WEBHOOK, headers=KEY)
    assert res.status_code == 200 and res.json()["body"]["2026-11-10"]["weight"] == 81.2
    anonymous.post(URL, json=HC_WEBHOOK, headers=KEY)  # the test button, then Sync Now, send the same records
    assert _day(session) == (7500, 405, 54)
    later = {"count": 500, "start_time": "2026-11-10T21:30:00+01:00", "end_time": "2026-11-10T21:45:00+01:00", "metadata": _meta("s3")}
    anonymous.post(URL, json=_batch(steps=[later]), headers=KEY)  # only new records
    assert _day(session) == (8000, 405, 54)
    anonymous.post(URL, json=_batch(steps=[{**later, "count": 700}]), headers=KEY)  # an edit keeps its id
    assert _day(session) == (8200, 405, 54)
    anonymous.post(URL, json=_batch(deleted=[{"type": "steps", "id": "s3"}]), headers=KEY)
    assert _day(session) == (7500, 405, 54)


def test_hc_webhook_empty_test_send_is_ok(anonymous):
    res = anonymous.post(URL, json=_batch(), headers=KEY)
    assert res.status_code == 200 and res.json()["days"] == 0
