import datetime as dt

import pytest

from db.models import SupplementLog
from services import clock


@pytest.fixture(autouse=True)
def utc_zone(monkeypatch):
    monkeypatch.setattr(clock, "system_zone", lambda: dt.timezone.utc)


def _quick(client, **fields):
    body = {"item_name": "Caffeine", "dosage": 200, "unit": "mg", "category": "stimulant", **fields}
    return client.post("/api/v1/supplements/quick", json=body)


def test_quick_log_stores_now_and_the_default_half_life(client, session):
    res = _quick(client)
    assert res.status_code == 201
    body = res.json()
    assert (body["item_name"], body["dosage"], body["unit"], body["half_life_hours"]) == ("Caffeine", 200, "mg", 5)
    assert dt.datetime.fromisoformat(body["timestamp"]).tzinfo is not None
    assert session.get(SupplementLog, body["id"]).item_name == "Caffeine"


def test_quick_log_accepts_a_timestamp_and_per_log_half_life(client):
    body = _quick(client, timestamp="2026-11-10T16:30:00Z", half_life_hours=6.5).json()
    assert body["timestamp"].startswith("2026-11-10T16:30:00") and body["half_life_hours"] == 6.5


def test_unknown_item_has_no_half_life(client):
    assert _quick(client, item_name="Zinc", category="supplement").json()["half_life_hours"] is None


def test_quick_log_rejects_blank_name_and_bad_category(client):
    assert _quick(client, item_name="  ").status_code == 422
    assert _quick(client, category="candy").status_code == 422


def test_list_is_newest_first_and_limited_by_days(client):
    now = dt.datetime.now(dt.timezone.utc)
    _quick(client, timestamp=(now - dt.timedelta(days=10)).isoformat())
    _quick(client, item_name="Magnesium", timestamp=(now - dt.timedelta(hours=3)).isoformat())
    latest = _quick(client, item_name="Melatonin").json()
    names = [row["item_name"] for row in client.get("/api/v1/supplements", params={"days": 7}).json()]
    assert names == ["Melatonin", "Magnesium"] and latest["id"]


def test_delete_removes_the_log_and_404s_twice(client):
    log_id = _quick(client).json()["id"]
    assert client.delete(f"/api/v1/supplements/{log_id}").status_code == 204
    assert client.delete(f"/api/v1/supplements/{log_id}").status_code == 404


def test_presets_default_then_replace(client):
    defaults = client.get("/api/v1/supplements/presets").json()
    assert defaults[0]["item_name"] == "Caffeine" and defaults[0]["half_life_hours"] == 5
    mine = [{"item_name": "Tea", "dosage": 50, "unit": "mg", "category": "stimulant", "half_life_hours": 4}]
    assert client.put("/api/v1/supplements/presets", json=mine).json() == mine
    assert client.get("/api/v1/supplements/presets").json() == mine


def test_preset_half_life_must_be_positive(client):
    bad = [{"item_name": "Tea", "dosage": 50, "unit": "mg", "category": "stimulant", "half_life_hours": 0}]
    assert client.put("/api/v1/supplements/presets", json=bad).status_code == 422


def test_quick_log_uses_a_preset_half_life_for_that_item(client):
    mine = [{"item_name": "Tea", "dosage": 50, "unit": "mg", "category": "stimulant", "half_life_hours": 4}]
    client.put("/api/v1/supplements/presets", json=mine)
    assert _quick(client, item_name="tea").json()["half_life_hours"] == 4


def test_bedtime_readout_decays_todays_stimulants(client):
    today = dt.datetime.now(dt.timezone.utc).date()
    _quick(client, timestamp=dt.datetime.combine(today, dt.time(16, 30), tzinfo=dt.timezone.utc).isoformat(), half_life_hours=6.5)
    _quick(client, item_name="Magnesium", category="supplement", dosage=400)
    readout = client.get("/api/v1/supplements/bedtime").json()
    assert readout["bedtime"] == "23:00"
    assert [(i["item_name"], i["unit"]) for i in readout["items"]] == [("Caffeine", "mg")]
    assert readout["items"][0]["remaining"] == pytest.approx(100)


def test_bedtime_readout_is_empty_without_stimulants(client):
    assert client.get("/api/v1/supplements/bedtime").json()["items"] == []
