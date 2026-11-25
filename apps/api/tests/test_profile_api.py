import datetime as dt

import pytest

from services import clock
from services.profile import bmi_category

TODAY = dt.date(2026, 11, 11)
RU = {"Accept-Language": "ru"}


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda zone=None: TODAY)


def _setup(client, birth="1990-11-12", height=180, sex="male"):
    return client.put("/api/v1/profile", json={"birth_date": birth, "height_cm": height, "sex": sex})


def _weigh(client, kg, date="2026-11-01"):
    return client.post("/api/v1/profile/measurements", json={"date": date, "kind": "weight", "value": kg})


def test_empty_profile_needs_birth_date(client):
    body = client.get("/api/v1/profile").json()
    assert body == {"birth_date": None, "age_years": None, "sex": None, "height_cm": None, "latest_weight": None,
                    "latest_waist": None, "bmi": None, "bmi_status": "needs_birth_date", "whtr": None}


def test_age_counts_whole_years_in_the_configured_day(client):
    assert _setup(client).json()["age_years"] == 35  # birthday is tomorrow
    assert client.put("/api/v1/profile", json={"birth_date": "1990-11-11"}).json()["age_years"] == 36


@pytest.mark.parametrize("bmi,category", [(18.4999, "underweight"), (18.5, "normal"), (24.99, "normal"), (25, "overweight"),
                                          (29.99, "overweight"), (30, "obese_1"), (34.99, "obese_1"), (35, "obese_2"),
                                          (39.99, "obese_2"), (40, "obese_3")])
def test_bmi_boundaries(bmi, category):
    assert bmi_category(bmi) == category


def test_bmi_is_classified_on_the_displayed_value(client):
    _setup(client, height=100)
    _weigh(client, 24.96)  # 24.96 is shown as 25.0, so it is overweight
    bmi = client.get("/api/v1/profile").json()["bmi"]
    assert bmi == {"value": 25.0, "category": "overweight", "date": "2026-11-01"}


def test_bmi_status_order_and_values(client):
    _setup(client, height=180)
    assert client.get("/api/v1/profile").json()["bmi_status"] == "needs_weight"
    client.put("/api/v1/profile", json={"height_cm": None})
    _weigh(client, 81)
    assert client.get("/api/v1/profile").json()["bmi_status"] == "needs_height"
    body = client.put("/api/v1/profile", json={"height_cm": 180}).json()
    assert body["bmi_status"] == "ok" and body["bmi"]["value"] == 25.0 and body["bmi"]["category"] == "overweight"
    assert body["latest_weight"] == {"date": "2026-11-01", "kg": 81}


def test_bmi_is_adults_only(client):
    _setup(client, birth="2010-01-01")
    _weigh(client, 50)
    body = client.get("/api/v1/profile").json()
    assert body["bmi"] is None and body["bmi_status"] == "adult_only"
    assert client.put("/api/v1/profile", json={"birth_date": "2008-11-11"}).json()["bmi_status"] == "ok"  # exactly 18


def test_missing_birth_date_blocks_bmi(client):
    client.put("/api/v1/profile", json={"height_cm": 180})
    _weigh(client, 80)
    body = client.get("/api/v1/profile").json()
    assert body["bmi"] is None and body["bmi_status"] == "needs_birth_date"


def test_whtr_from_latest_waist(client):
    _setup(client, height=180)
    client.post("/api/v1/profile/measurements", json={"date": "2026-11-02", "kind": "waist", "value": 90})
    body = client.get("/api/v1/profile").json()
    assert body["whtr"] == 0.5 and body["latest_waist"] == {"date": "2026-11-02", "cm": 90}


def test_put_is_partial_and_null_clears(client):
    _setup(client)
    body = client.put("/api/v1/profile", json={"sex": "female"}).json()
    assert body["sex"] == "female" and body["height_cm"] == 180 and body["birth_date"] == "1990-11-12"
    body = client.put("/api/v1/profile", json={"sex": None, "height_cm": None}).json()
    assert body["sex"] is None and body["height_cm"] is None and body["birth_date"] == "1990-11-12"


@pytest.mark.parametrize("body,en,ru", [
    ({"birth_date": "2026-11-12"}, "not in the future", "не из будущего"),
    ({"birth_date": "1899-12-31"}, "not before 1900", "не раньше 1900"),
    ({"sex": "other"}, "female or male", "женским или мужским"),
    ({"height_cm": 49}, "between 50 and 260", "от 50 до 260"),
    ({"height_cm": 261}, "between 50 and 260", "от 50 до 260"),
])
def test_profile_validation_is_localized(client, body, en, ru):
    r = client.put("/api/v1/profile", json=body)
    assert r.status_code == 422 and en in r.json()["detail"]
    r = client.put("/api/v1/profile", json=body, headers=RU)
    assert r.status_code == 422 and ru in r.json()["detail"]


def test_measurement_same_day_replaces_and_lists_newest_first(client):
    first = _weigh(client, 80, "2026-11-01")
    assert first.status_code == 201 and first.json()["value"] == 80
    again = _weigh(client, 79, "2026-11-01")
    assert again.json()["id"] == first.json()["id"]
    _weigh(client, 78, "2026-11-05")
    client.post("/api/v1/profile/measurements", json={"date": "2026-11-05", "kind": "waist", "value": 90})
    rows = client.get("/api/v1/profile/measurements?kind=weight").json()
    assert [(r["date"], r["value"]) for r in rows] == [("2026-11-05", 78), ("2026-11-01", 79)]
    assert rows[0].keys() == {"id", "date", "kind", "value"}
    assert len(client.get("/api/v1/profile/measurements").json()) == 3


def test_delete_measurement(client):
    mid = _weigh(client, 80).json()["id"]
    assert client.delete(f"/api/v1/profile/measurements/{mid}").status_code == 204
    assert client.get("/api/v1/profile/measurements").json() == []
    r = client.delete(f"/api/v1/profile/measurements/{mid}")
    assert r.status_code == 404 and r.json()["detail"] == "No such measurement"
    assert client.delete(f"/api/v1/profile/measurements/{mid}", headers=RU).json()["detail"] == "Такого измерения нет"


@pytest.mark.parametrize("body,en,ru", [
    ({"date": "2026-11-01", "kind": "weight", "value": 19.9}, "Weight must be between 20 and 400 kg", "Вес должен быть от 20 до 400 кг"),
    ({"date": "2026-11-01", "kind": "weight", "value": 401}, "Weight must be", "Вес должен"),
    ({"date": "2026-11-01", "kind": "waist", "value": 29}, "Waist must be between 30 and 250 cm", "Талия должна быть от 30 до 250 см"),
    ({"date": "2026-11-12", "kind": "weight", "value": 80}, "cannot be in the future", "не может быть в будущем"),
    ({"date": "2026-11-01", "kind": "height", "value": 80}, "must be one of: weight, waist, body_fat_pct", "должен быть одним из: weight, waist, body_fat_pct"),
])
def test_measurement_validation_is_localized(client, body, en, ru):
    r = client.post("/api/v1/profile/measurements", json=body)
    assert r.status_code == 422 and en in r.json()["detail"]
    assert ru in client.post("/api/v1/profile/measurements", json=body, headers=RU).json()["detail"]


def test_bmi_history_uses_current_height_and_fixed_bands(client):
    _setup(client, height=180)
    _weigh(client, 90, "2026-10-01")
    _weigh(client, 60, "2026-11-01")
    h = client.get("/api/v1/profile/bmi-history").json()
    assert h["height_cm"] == 180 and h["note"] == "Calculated with your current height."
    assert h["points"] == [{"date": "2026-10-01", "weight_kg": 90, "bmi": 27.8, "category": "overweight"},
                           {"date": "2026-11-01", "weight_kg": 60, "bmi": 18.5, "category": "normal"}]
    assert h["bands"] == [{"key": "underweight", "min": None, "max": 18.5}, {"key": "normal", "min": 18.5, "max": 25},
                          {"key": "overweight", "min": 25, "max": 30}, {"key": "obese", "min": 30, "max": None}]
    assert client.get("/api/v1/profile/bmi-history", headers=RU).json()["note"] == "Рассчитано по вашему текущему росту."


def test_bmi_history_is_empty_without_height_or_weights(client):
    _weigh(client, 80)
    assert client.get("/api/v1/profile/bmi-history").json()["points"] == []
    _setup(client)
    client.delete("/api/v1/profile/measurements/1")
    assert client.get("/api/v1/profile/bmi-history").json()["points"] == []
