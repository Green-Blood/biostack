import datetime as dt

import pytest
from sqlmodel import select

from db.models import BodyMeasurement, DailyMetric
from services import clock
from services.health_payload import parse_body
from tests.test_health_sync import AUTO_EXPORT, KEY, URL, anonymous  # noqa: F401

RU = {"Accept-Language": "ru"}
DAY = dt.date(2026, 11, 10)


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda zone=None: dt.date(2026, 11, 11))


def _post(client, kind, value, date="2026-11-01"):
    return client.post("/api/v1/profile/measurements", json={"date": date, "kind": kind, "value": value})


@pytest.mark.parametrize("kind,lo,hi", [("body_fat_pct", 2, 70), ("muscle_kg", 5, 120), ("body_water_pct", 20, 80),
                                        ("bone_kg", 0.5, 10), ("visceral_fat", 1, 60), ("bmr_kcal", 500, 5000)])
def test_new_kinds_accept_their_range_and_reject_outside(client, kind, lo, hi):
    assert _post(client, kind, lo).status_code == 201 and _post(client, kind, hi, "2026-11-02").status_code == 201
    low = _post(client, kind, lo - 0.01, "2026-11-03")
    assert low.status_code == 422 and "must be between" in low.json()["detail"]
    assert _post(client, kind, hi + 1, "2026-11-03").status_code == 422
    assert "от" in client.post("/api/v1/profile/measurements", json={"date": "2026-11-03", "kind": kind, "value": hi + 1}, headers=RU).json()["detail"]
    assert len(client.get("/api/v1/profile/measurements", params={"kind": kind}).json()) == 2


def test_list_without_kind_returns_all_kinds(client):
    _post(client, "weight", 80)
    _post(client, "bone_kg", 3)
    assert {m["kind"] for m in client.get("/api/v1/profile/measurements").json()} == {"weight", "bone_kg"}


def test_body_endpoint_latest_and_previous(client):
    assert client.get("/api/v1/profile/body").json() == {"latest": {}, "previous": {}}
    _post(client, "weight", 82, "2026-10-01")
    _post(client, "weight", 81, "2026-10-15")
    _post(client, "weight", 80, "2026-11-01")
    _post(client, "muscle_kg", 35, "2026-11-01")
    assert client.get("/api/v1/profile/body").json() == {
        "latest": {"weight": {"date": "2026-11-01", "value": 80}, "muscle_kg": {"date": "2026-11-01", "value": 35}},
        "previous": {"weight": {"date": "2026-10-15", "value": 81}}}


def test_auto_export_body_metrics():
    payload = {"data": {"metrics": [
        {"name": "weight_body_mass", "units": "lb", "data": [{"date": "2026-11-10 07:00:00 +0100", "qty": 180}]},
        {"name": "body_fat_percentage", "units": "%", "data": [{"date": "2026-11-10 07:00:00 +0100", "qty": 18.5}]},
        {"name": "waist_circumference", "units": "in", "data": [{"date": "2026-11-10 07:00:00 +0100", "qty": 35}]},
        {"name": "lean_body_mass", "units": "kg", "data": [{"date": "2026-11-10 07:00:00 +0100", "qty": 60}]},
    ]}}
    assert parse_body(payload) == {DAY: {"weight": 81.65, "body_fat_pct": 18.5, "waist": 88.9}}


def test_body_fat_fraction_rule():
    def fat(qty, units):
        return parse_body({"data": {"metrics": [{"name": "body_fat_percentage", "units": units, "data": [{"date": "2026-11-10", "qty": qty}]}]}})
    assert fat(0.185, "%") == {DAY: {"body_fat_pct": 18.5}} and fat(0.185, "") == {DAY: {"body_fat_pct": 18.5}}
    assert fat(18.5, "%") == {DAY: {"body_fat_pct": 18.5}}
    assert fat(0.185, "count") == {}  # a unit we do not know is not guessed at


def test_latest_reading_of_the_day_wins():
    payload = {"data": {"metrics": [{"name": "weight_body_mass", "units": "kg", "data": [
        {"date": "2026-11-10 21:00:00 +0100", "qty": 82}, {"date": "2026-11-10 07:00:00 +0100", "qty": 80}]}]}}
    assert parse_body(payload) == {DAY: {"weight": 82}}


def test_flat_body_keys_and_bad_values_are_dropped():
    flat = {"date": "2026-11-10", "weight_kg": 80, "body_fat_pct": 18, "muscle_kg": "lots", "waist_cm": float("nan"),
            "bone_kg": 99, "weight_lb": None, "body_water_pct": True}
    assert parse_body(flat) == {DAY: {"weight": 80, "body_fat_pct": 18}}
    assert parse_body({"date": "2026-11-10", "weight_lb": 200}) == {DAY: {"weight": 90.72}}
    assert parse_body({"date": "bad", "weight_kg": 80}) == {} and parse_body([]) == {}


def test_webhook_stores_body_and_leaves_daily_metrics_alone(anonymous, session):  # noqa: F811
    res = anonymous.post(URL, json={"date": "2026-11-10", "weight_kg": 80.5, "waist_cm": 90, "steps": 5000}, headers=KEY)
    assert res.status_code == 200 and res.json()["dates"] == ["2026-11-10"]
    rows = {m.kind: (m.value, m.source) for m in session.exec(select(BodyMeasurement))}
    assert rows == {"weight": (80.5, "sync"), "waist": (90, "sync")}
    assert session.get(DailyMetric, DAY).steps == 5000


def test_webhook_body_only_payload_is_ok_and_upserts(anonymous, session):  # noqa: F811
    anonymous.post(URL, json={"date": "2026-11-10", "weight_kg": 80}, headers=KEY)
    res = anonymous.post(URL, json={"date": "2026-11-10", "weight_kg": 79, "body_fat_pct": 17}, headers=KEY)
    assert res.status_code == 200
    session.expire_all()
    assert {m.kind: m.value for m in session.exec(select(BodyMeasurement))} == {"weight": 79, "body_fat_pct": 17}
    assert session.get(DailyMetric, DAY) is None


def test_webhook_only_bad_body_values_is_still_422(anonymous):  # noqa: F811
    assert anonymous.post(URL, json={"date": "2026-11-10", "weight_kg": "x", "muscle_kg": 1}, headers=KEY).status_code == 422


def test_webhook_mixed_auto_export_with_body(anonymous, session):  # noqa: F811
    payload = {"data": {"metrics": AUTO_EXPORT["data"]["metrics"] + [
        {"name": "weight_body_mass", "units": "kg", "data": [{"date": "2026-11-10 07:00:00 +0100", "qty": 80}]}]}}
    assert anonymous.post(URL, json=payload, headers=KEY).status_code == 200
    assert session.exec(select(BodyMeasurement)).one().value == 80
    assert session.get(DailyMetric, DAY).steps == 7500
