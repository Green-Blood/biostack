"""Backend review fixes: body data, CSV import, BMI, briefing stamp, AI context, health sync."""
import datetime as dt

import pytest
from sqlalchemy import event
from sqlmodel import select

from db.models import BodyMeasurement
from services import clock
from tests.test_body_import import IMPORT, RU, TODAY, rows, up  # noqa: F401
from tests.test_health_sync import KEY, URL, anonymous  # noqa: F401

DAY = dt.date(2026, 11, 10)


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda zone=None: TODAY)


def _weigh(client, kg, date="2026-11-01"):
    return client.post("/api/v1/profile/measurements", json={"date": date, "kind": "weight", "value": kg})


def _setup(client, birth="1990-11-12", height=180, sex="male"):
    return client.put("/api/v1/profile", json={"birth_date": birth, "height_cm": height, "sex": sex})


# ---- I1: a sync never overwrites a hand-entered value ----

def test_sync_keeps_a_manual_value_and_counts_it(anonymous, client, session):  # noqa: F811
    assert _weigh(client, 80, "2026-11-10").status_code == 201
    res = anonymous.post(URL, json={"date": "2026-11-10", "weight_kg": 79, "body_fat_pct": 17}, headers=KEY)
    assert res.status_code == 200 and res.json()["body"]["skipped_manual"] == 1
    session.expire_all()
    rows_ = {m.kind: (m.value, m.source) for m in session.exec(select(BodyMeasurement))}
    assert rows_ == {"weight": (80, "manual"), "body_fat_pct": (17, "sync")}


def test_sync_still_replaces_an_earlier_sync_and_csv_still_replaces_manual(anonymous, client, session):  # noqa: F811
    anonymous.post(URL, json={"date": "2026-11-10", "weight_kg": 80}, headers=KEY)
    anonymous.post(URL, json={"date": "2026-11-10", "weight_kg": 79}, headers=KEY)
    session.expire_all()
    assert session.exec(select(BodyMeasurement)).one().value == 79
    _weigh(client, 70, "2026-11-10")
    up(client, "Date,Weight\n2026-11-10,75\n", dry=False)
    session.expire_all()
    assert session.exec(select(BodyMeasurement)).one().value == 75


# ---- I2: units in the raw header ----

@pytest.mark.parametrize("header", ["Skeletal Muscle(%)", "Muscle(%)", "Muscle Mass (%)", "Bone (%)", "Weight (%)"])
def test_a_percent_column_is_never_a_kg_kind(client, header):
    body = up(client, f"Date,Weight (kg),{header}\n2026-11-01,80,50\n").json()
    assert rows(body) == {"2026-11-01": {"weight": 80}}
    assert any(header in w for w in body["warnings"])
    assert next(c for c in body["columns"] if c["header"] == header)["mapped_to"] is None


@pytest.mark.parametrize("header", ["Body Water (kg)", "Body Fat (lb)", "Water Mass", "Fat (kg)"])
def test_a_kg_column_is_never_a_percent_kind(client, header):
    body = up(client, f"Date,Weight,{header}\n2026-11-01,80,40\n").json()
    assert rows(body) == {"2026-11-01": {"weight": 80}}


def test_matching_units_still_map(client):
    body = up(client, "Date,Weight (kg),Body Fat (%),Muscle (kg),Water (%)\n2026-11-01,80,20,35,55\n").json()
    assert rows(body) == {"2026-11-01": {"weight": 80, "body_fat_pct": 20, "muscle_kg": 35, "body_water_pct": 55}}


# ---- I3: decimal commas in a comma file ----

def test_a_row_with_more_cells_than_the_header_is_skipped_not_truncated(client):
    body = up(client, "Date,Weight\n2026-11-01,72,5\n2026-11-02,73\n").json()
    assert rows(body) == {"2026-11-02": {"weight": 73}}
    assert body["skipped_total"] == 1 and body["skipped"][0]["line"] == 2
    ru = up(client, "Date,Weight\n2026-11-01,72,5\n2026-11-02,73\n", headers=RU).json()
    assert ru["skipped"][0]["reason"] != body["skipped"][0]["reason"]


def test_quoted_decimal_comma_in_a_comma_file_warns(client):
    body = up(client, 'Date,Weight\n2026-11-01,"72,5"\n').json()
    assert rows(body) == {"2026-11-01": {"weight": 72.5}}
    assert any("comma" in w.lower() for w in body["warnings"])
    assert not any("comma" in w.lower() for w in up(client, "Date;Weight\n2026-11-01;72,5\n").json()["warnings"])


# ---- I4: BMI history follows the adult rule ----

def test_bmi_history_has_no_points_without_a_birth_date_or_for_a_minor(client):
    client.put("/api/v1/profile", json={"height_cm": 180})
    _weigh(client, 80)
    h = client.get("/api/v1/profile/bmi-history").json()
    assert h["points"] == [] and h["bmi_status"] == "needs_birth_date" and len(h["bands"]) == 4
    client.put("/api/v1/profile", json={"birth_date": "2015-01-01"})
    h = client.get("/api/v1/profile/bmi-history").json()
    assert h["points"] == [] and h["bmi_status"] == "adult_only"


def test_bmi_history_for_an_adult_has_points_and_status_ok(client):
    _setup(client)
    _weigh(client, 90)
    h = client.get("/api/v1/profile/bmi-history").json()
    assert h["bmi_status"] == "ok" and len(h["points"]) == 1


# ---- I6: the preview counts days as well as values ----

def test_import_preview_counts_replaced_days(client):
    _weigh(client, 70, "2026-11-01")
    client.post("/api/v1/profile/measurements", json={"date": "2026-11-01", "kind": "waist", "value": 90})
    text = "Date,Weight,Body fat\n2026-11-01,80,20\n2026-11-02,81,21\n"
    dry = up(client, text).json()
    assert dry["would_replace"] == 1 and dry["would_replace_days"] == 1 and dry["replaced_days"] == 0
    real = up(client, text, dry=False).json()
    assert real["replaced"] == 1 and real["replaced_days"] == 1 and real["would_replace_days"] == 1


def test_would_replace_days_counts_a_day_once_for_several_kinds(client):
    _weigh(client, 70, "2026-11-01")
    client.post("/api/v1/profile/measurements", json={"date": "2026-11-01", "kind": "body_fat_pct", "value": 20})
    body = up(client, "Date,Weight,Body fat\n2026-11-01,80,19\n").json()
    assert body["would_replace"] == 2 and body["would_replace_days"] == 1


# ---- minor: BMI category follows the displayed value ----

@pytest.mark.parametrize("height,kg,shown,category", [(100, 24.96, 25.0, "overweight"), (110, 22.34, 18.5, "normal")])
def test_category_is_chosen_on_the_rounded_value(client, height, kg, shown, category):
    _setup(client, height=height)
    _weigh(client, kg)
    bmi = client.get("/api/v1/profile").json()["bmi"]
    assert (bmi["value"], bmi["category"]) == (shown, category)
    point = client.get("/api/v1/profile/bmi-history").json()["points"][0]
    assert (point["bmi"], point["category"]) == (shown, category)


# ---- minor: CSV robustness ----

def test_an_overlong_field_is_a_localized_422_not_a_crash(client):
    r = up(client, "Date,Weight\n2026-11-01," + "9" * 200_000 + "\n")
    assert r.status_code == 422 and "UTF-8" in r.json()["detail"]
    assert "Не удалось" in up(client, "Date,Weight\n2026-11-01," + "9" * 200_000 + "\n", headers=RU).json()["detail"]


def test_a_cell_spanning_lines_warns_that_rows_may_have_merged(client):
    body = up(client, 'Date,Weight,Note\n2026-11-01,80,"oops\n2026-11-02,81,fine\n2026-11-03,82,x\n').json()
    assert any("several lines" in w for w in body["warnings"])
    assert any("несколько строк" in w for w in up(client, 'Date,Weight,Note\n2026-11-01,80,"oops\n2026-11-02,81,fine\n', headers=RU).json()["warnings"])


def test_timestamps_with_an_offset_use_the_owners_time_zone(client):
    client.put("/api/v1/settings", json={"latitude": None, "longitude": None, "bedtime": "23:00", "timezone": "Asia/Tokyo"})
    body = up(client, "Date,Weight\n2026-11-01T20:00:00Z,80\n2026-11-02T18:00:00-08:00,81\n").json()
    # 20:00Z is 05:00 on the 2nd in Tokyo; 18:00 at -08:00 is 11:00 on the 3rd in Tokyo
    assert rows(body) == {"2026-11-02": {"weight": 80}, "2026-11-03": {"weight": 81}}
    plain = up(client, "Date,Weight\n2026-11-01 23:30,80\n").json()  # no offset: the day as written
    assert rows(plain) == {"2026-11-01": {"weight": 80}}


def test_existing_days_chunks_its_in_list(session):
    from services.profile import existing_days
    start = dt.date(2020, 1, 1)
    keys = {(start + dt.timedelta(days=i), "weight") for i in range(1200)}
    session.add(BodyMeasurement(measured_on=start, kind="weight", value=70))
    session.commit()
    sizes: list[int] = []

    @event.listens_for(session.get_bind(), "before_cursor_execute")
    def _spy(conn, cursor, statement, parameters, context, executemany):
        sizes.append(len(parameters))

    assert existing_days(session, keys) == 1
    assert sizes and max(sizes) <= 500


# ---- minor: health sync reports a real payload error next to the body ----

def test_a_real_daily_metrics_error_is_reported_with_the_body(anonymous, session):  # noqa: F811
    payload = {"data": {"metrics": [{"name": "weight_body_mass", "units": "kg", "data": [{"date": "2026-11-10", "qty": 80}]},
                                    {"name": "step_count", "data": [{"date": "bad date", "qty": 5}]}]}}
    res = anonymous.post(URL, json=payload, headers=KEY)
    assert res.status_code == 200 and "date" in res.json()["daily_metrics_error"]
    assert session.exec(select(BodyMeasurement)).one().value == 80


def test_a_body_only_payload_has_no_daily_metrics_error(anonymous):  # noqa: F811
    res = anonymous.post(URL, json={"date": "2026-11-10", "weight_kg": 80}, headers=KEY)
    assert res.status_code == 200 and "daily_metrics_error" not in res.json()


# ---- minor: the measurement-kind message lists the kinds ----

def test_measurement_kind_message_lists_all_kinds(client):
    from services.profile import KINDS
    r = client.post("/api/v1/profile/measurements", json={"date": "2026-11-01", "kind": "height", "value": 80})
    assert all(k in r.json()["detail"] for k in KINDS)
    ru = client.post("/api/v1/profile/measurements", json={"date": "2026-11-01", "kind": "height", "value": 80}, headers=RU)
    assert all(k in ru.json()["detail"] for k in KINDS)
