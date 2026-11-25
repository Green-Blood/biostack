import datetime as dt

import pytest
from sqlmodel import select

from db.models import BodyMeasurement
from services import clock

TODAY = dt.date(2026, 11, 11)
RU = {"Accept-Language": "ru"}
IMPORT = "/api/v1/profile/measurements/import"


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda zone=None: TODAY)


def up(client, content, dry=True, headers=None, name="scale.csv", ctype="text/csv"):
    data = content.encode("utf-8") if isinstance(content, str) else content
    return client.post(IMPORT, params={"dry_run": str(dry).lower()}, files={"file": (name, data, ctype)}, headers=headers or {})


def rows(body):
    return {r["date"]: r["values"] for r in body["rows"]}


@pytest.mark.parametrize("delim,label", [(",", ","), (";", ";"), ("\t", "\t")])
def test_delimiters_are_sniffed(client, delim, label):
    csv_text = delim.join(["Date", "Weight", "Body fat"]) + "\n" + delim.join(["2026-11-01", "80.5", "18.2"]) + "\n"
    body = up(client, csv_text).json()
    assert body["delimiter"] == label and body["encoding"] == "utf-8"
    assert rows(body) == {"2026-11-01": {"weight": 80.5, "body_fat_pct": 18.2}}
    assert body["imported"] == 0 and body["total_rows"] == 1


def test_cp1251_russian_headers_and_decimal_comma(client):
    text = "Дата;Вес (кг);Процент жира;Мышечная масса;Вода в организме;Кости;Висцеральный жир;Основной обмен;Талия;ИМТ\n10.11.2026 08:30;80,5;18,2;35;55;3,1;9;1800;90;24,8\n"
    body = up(client, text.encode("cp1251")).json()
    assert body["encoding"] == "cp1251" and body["day_first"] is True
    assert rows(body) == {"2026-11-10": {"weight": 80.5, "body_fat_pct": 18.2, "muscle_kg": 35, "body_water_pct": 55,
                                         "bone_kg": 3.1, "visceral_fat": 9, "bmr_kcal": 1800, "waist": 90}}
    mapped = {c["header"]: c["mapped_to"] for c in body["columns"]}
    assert mapped["ИМТ"] is None and mapped["Дата"] == "date" and mapped["Вес (кг)"] == "weight"
    assert any("ИМТ" in w for w in body["warnings"])


def test_pounds_header_converts_to_kg(client):
    body = up(client, "date,weight lb\n2026-11-01,180\n").json()
    assert rows(body)["2026-11-01"]["weight"] == 81.65


def test_day_first_detected_from_a_big_first_part(client):
    body = up(client, "date,weight\n13/01/2026,80\n05/02/2026,81\n").json()
    assert body["day_first"] is True and set(rows(body)) == {"2026-01-13", "2026-02-05"} and body["warnings"] == []


def test_month_first_detected_from_a_big_second_part(client):
    body = up(client, "date,weight\n01/13/2026,80\n02/05/2026,81\n").json()
    assert body["day_first"] is False and set(rows(body)) == {"2026-01-13", "2026-02-05"}


def test_ambiguous_dates_default_to_day_first_with_a_warning(client):
    body = up(client, "date,weight\n03/04/2026,80\n").json()
    assert body["day_first"] is True and set(rows(body)) == {"2026-04-03"}
    assert len(body["warnings"]) == 1 and "day first" in body["warnings"][0]
    ru = up(client, "date,weight\n03/04/2026,80\n", headers=RU).json()
    assert "день-месяц" in ru["warnings"][0]


def test_iso_with_time_and_t_separator(client):
    body = up(client, "date,weight\n2026-11-01T07:30:00,80\n2026/11/02,81\n").json()
    assert set(rows(body)) == {"2026-11-01", "2026-11-02"}


def test_separate_date_and_time_columns_latest_time_wins(client):
    body = up(client, "Date,Time,Weight\n2026-11-01,08:00,80\n2026-11-01,21:00,82\n2026-11-01,12:00,81\n").json()
    assert rows(body) == {"2026-11-01": {"weight": 82}} and body["total_rows"] == 1


def test_same_day_latest_time_wins_with_full_timestamps(client):
    body = up(client, "timestamp,weight\n2026-11-01 21:00,82\n2026-11-01 08:00,80\n").json()
    assert rows(body)["2026-11-01"]["weight"] == 82


def test_future_dates_skipped_and_counted(client):
    body = up(client, "date,weight\n2026-11-12,80\n2026-11-11,81\n").json()
    assert set(rows(body)) == {"2026-11-11"} and body["skipped"] == [{"line": 2, "reason": "Date 2026-11-12 is in the future."}]


def test_out_of_range_is_skipped_with_reason_never_clamped(client):
    text = "date,weight,body fat\n2026-11-01,500,18\n2026-11-02,80,abc\n"
    body = up(client, text).json()
    assert rows(body) == {"2026-11-01": {"body_fat_pct": 18}, "2026-11-02": {"weight": 80}}  # the good value of a half-bad row is kept
    reasons = [s["reason"] for s in body["skipped"]]
    assert reasons == ["Weight: 500 is outside 20 to 400.", 'Body fat: "abc" is not a number.']
    ru = up(client, text, headers=RU).json()["skipped"][0]["reason"]
    assert ru == "Вес: 500 вне диапазона от 20 до 400."


def test_bad_date_and_empty_row_reasons(client):
    body = up(client, "date,weight\nyesterday,80\n2026-11-01,\n").json()
    assert [s["line"] for s in body["skipped"]] == [2, 3] and body["rows"] == []


def test_dry_run_writes_nothing_and_real_import_replaces(client, session):
    client.post("/api/v1/profile/measurements", json={"date": "2026-11-01", "kind": "weight", "value": 70})
    text = "date,weight,body fat\n2026-11-01,80,18\n2026-11-02,81,19\n"
    dry = up(client, text).json()
    assert dry["imported"] == 0 and dry["replaced"] == 0 and dry["would_replace"] == 1
    assert len(session.exec(select(BodyMeasurement)).all()) == 1
    real = up(client, text, dry=False).json()
    assert real["imported"] == 4 and real["replaced"] == 1
    session.expire_all()
    by_key = {(m.measured_on.isoformat(), m.kind): (m.value, m.source) for m in session.exec(select(BodyMeasurement))}
    assert by_key[("2026-11-01", "weight")] == (80, "csv") and len(by_key) == 4


def test_preview_is_capped_but_total_is_real(client):
    start = dt.date(2025, 1, 1)
    text = "date,weight\n" + "".join(f"{(start + dt.timedelta(days=i)).isoformat()},80\n" for i in range(250))
    body = up(client, text).json()
    assert len(body["rows"]) == 200 and body["total_rows"] == 250


def test_file_errors(client):
    big = up(client, b"date,weight\n" + b"2026-11-01,80\n" * 200000)
    assert big.status_code == 413 and "2 MB" in big.json()["detail"]
    assert "2 МБ" in up(client, b"x" * (2 * 1024 * 1024 + 1), headers=RU).json()["detail"]
    png = up(client, b"\x89PNG\r\n\x1a\n\x00\x00", name="a.png", ctype="image/png")
    assert png.status_code == 415 and "CSV" in png.json()["detail"]
    assert up(client, b"PK\x03\x04\x00\x00", name="a.csv").status_code == 415
    assert up(client, "foo,bar\n1,2\n").status_code == 422
    assert up(client, "date,bar\n2026-11-01,2\n").status_code == 422
    assert up(client, "date,weight\n").status_code == 422
    assert "Не найден столбец" in up(client, "foo,weight\n1,2\n", headers=RU).json()["detail"]
