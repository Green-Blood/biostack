"""Body signals read API. All data is synthetic."""
import datetime as dt

import pytest
from sqlalchemy import event

from db.models import BodyMeasurement, DailyMetric, ImportJob, SleepSession, SleepStage, Workout
from services import clock, signals

D = dt.date
TODAY = D(2026, 11, 12)


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda zone=None: TODAY)


def _daily(session, date, **fields):
    session.add(DailyMetric(metric_date=date, source="samsung_export", **fields))


def _part(session, wake, start_hm, end_hm, ext, off=300, main=True, **kw):
    """A sleep part ending on local date `wake`; start/end are local HH:MM, stored as UTC with the offset applied."""
    sh, sm = start_hm
    eh, em = end_hm
    end_local = dt.datetime(wake.year, wake.month, wake.day, eh, em)
    start_local = dt.datetime(wake.year, wake.month, wake.day, sh, sm)
    if start_local >= end_local:
        start_local -= dt.timedelta(days=1)
    delta = dt.timedelta(minutes=off)
    part = SleepSession(source="samsung_export", external_id=ext, start_utc=(start_local - delta).replace(tzinfo=dt.UTC), end_utc=(end_local - delta).replace(tzinfo=dt.UTC),
                        tz_offset_min=off, wake_date=wake, duration_min=kw.pop("duration_min", 400), is_main=main, **kw)
    session.add(part)
    session.commit()
    session.refresh(part)
    return part


def _night_row(session, wake, total=420.0):
    _daily(session, wake, sleep_total_min=total, sleep_deep_min=70, sleep_rem_min=90, sleep_light_min=240,
           sleep_awake_min=20, sleep_efficiency=92)


def _count_queries(client, engine, url):
    n = []
    def hook(conn, cursor, statement, params, context, many):
        n.append(statement)
    event.listen(engine, "before_cursor_execute", hook)
    try:
        res = client.get(url)
    finally:
        event.remove(engine, "before_cursor_execute", hook)
    assert res.status_code == 200, res.text
    return len(n)


# ---- band math ----

def test_band_needs_ten_points():
    assert signals.band([float(i) for i in range(9)]) is None
    b = signals.band([float(i) for i in range(1, 11)])
    assert b == {"p25": 3.25, "p75": 7.75}


def test_position_words():
    b = {"p25": 10.0, "p75": 20.0}
    assert signals.position(9.9, b) == "below"
    assert signals.position(10.0, b) == "within"
    assert signals.position(20.0, b) == "within"
    assert signals.position(20.1, b) == "above"
    assert signals.position(5.0, None) is None


def _hr_history(session, n, start_value=50):
    for i in range(n):
        _daily(session, TODAY - dt.timedelta(days=1 + i), resting_hr=float(start_value + i))
    session.commit()


def _tile(body, key):
    return next(t for t in body["tiles"] if t["key"] == key)


@pytest.mark.parametrize("offset,values,expected", [
    (0, [350, 400], True), (1, [350, 400], True), (2, [350, 400], False),
    (0, [350, 420], False), (0, [350, None], False), (0, [0, 350], False),
])
def test_short_sleep_insight_requires_two_recent_consecutive_nights(client, session, offset, values, expected):
    for i, value in enumerate(values):
        if value is not None:
            _daily(session, TODAY - dt.timedelta(days=offset + i), sleep_total_min=value)
    session.commit()
    result = client.get("/api/v1/signals/overview").json()["short_sleep_end"]
    assert result == ((TODAY - dt.timedelta(days=offset)).isoformat() if expected else None)


def test_overview_tiles_exact_keys_and_empty(client):
    body = client.get("/api/v1/signals/overview").json()
    assert [t["key"] for t in body["tiles"]] == ["sleep_total_min", "resting_hr", "hrv_sdnn", "skin_temp_delta",
                                                  "spo2_avg", "steps", "weight"]
    assert body["has_data"] is False and body["last_night"] is None and body["latest_import"] is None
    assert all(t["value"] is None and t["band"] is None and t["position"] is None and t["spark"] == [] for t in body["tiles"])


@pytest.mark.parametrize("value,pos", [(40.0, "below"), (55.0, "within"), (99.0, "above")])
def test_overview_band_and_position(client, session, value, pos):
    _hr_history(session, 12)  # 50..61, previous 12 days
    _daily(session, TODAY, resting_hr=value)
    session.commit()
    t = _tile(client.get("/api/v1/signals/overview").json(), "resting_hr")
    assert t["value"] == value and t["date"] == TODAY.isoformat()
    assert t["band"] == {"p25": 52.75, "p75": 58.25}
    assert t["position"] == pos


def test_overview_band_excludes_shown_day_and_needs_ten(client, session):
    _hr_history(session, 9)
    _daily(session, TODAY, resting_hr=70.0)
    session.commit()
    t = _tile(client.get("/api/v1/signals/overview").json(), "resting_hr")
    assert t["band"] is None and t["position"] is None  # 9 previous points; today's own value does not count


def test_overview_stale_value_is_null_but_spark_kept(client, session):
    _daily(session, TODAY - dt.timedelta(days=10), steps=8000)
    _daily(session, TODAY - dt.timedelta(days=6), steps=5000)
    session.commit()
    t = _tile(client.get("/api/v1/signals/overview").json(), "steps")
    assert t["value"] == 5000 and t["date"] == (TODAY - dt.timedelta(days=6)).isoformat()
    assert [p["value"] for p in t["spark"]] == [8000, 5000]


def test_overview_stale_beyond_seven_days(client, session):
    _daily(session, TODAY - dt.timedelta(days=7), steps=8000)
    session.commit()
    t = _tile(client.get("/api/v1/signals/overview").json(), "steps")
    assert t["value"] is None and t["date"] is None and len(t["spark"]) == 1


def test_overview_weight_tile_and_has_data(client, session):
    session.add(BodyMeasurement(measured_on=TODAY - dt.timedelta(days=2), kind="weight", value=80.5, source="manual"))
    session.add(BodyMeasurement(measured_on=TODAY - dt.timedelta(days=2), kind="waist", value=90, source="manual"))
    session.commit()
    body = client.get("/api/v1/signals/overview").json()
    t = _tile(body, "weight")
    assert t["value"] == 80.5 and t["unit"] == "kg" and t["spark"] == [{"date": (TODAY - dt.timedelta(days=2)).isoformat(), "value": 80.5}]
    assert body["has_data"] is True


def test_overview_names_localized(client):
    en = _tile(client.get("/api/v1/signals/overview").json(), "resting_hr")
    ru = _tile(client.get("/api/v1/signals/overview", headers={"Accept-Language": "ru"}).json(), "resting_hr")
    assert en["name"] != ru["name"] and en["unit"] != ru["unit"]


def test_overview_last_night_merged_parts_and_latest_import(client, session):
    wake = TODAY - dt.timedelta(days=1)
    _night_row(session, wake, total=420)
    a = _part(session, wake, (23, 0), (3, 0), "a", off=300)
    _part(session, wake, (3, 30), (7, 15), "b", off=300)
    _part(session, wake, (14, 0), (14, 30), "nap", off=300, main=False)
    session.add(ImportJob(kind="samsung_health", status="done", progress=1, summary={"nights": 3},
                          finished_at=dt.datetime(2026, 11, 10, 8, 0, tzinfo=dt.UTC)))
    session.add(ImportJob(kind="samsung_health", status="failed", error="x", finished_at=dt.datetime(2026, 11, 11, 8, 0, tzinfo=dt.UTC)))
    session.commit()
    body = client.get("/api/v1/signals/overview").json()
    n = body["last_night"]
    assert n["session_id"] == a.id and n["wake_date"] == wake.isoformat()
    assert n["start_local"] == f"{wake - dt.timedelta(days=1)}T23:00:00"
    assert n["end_local"] == f"{wake}T07:15:00"
    assert n["duration_min"] == 420 and n["stages"] == {"deep": 70, "rem": 90, "light": 240, "awake": 20}
    assert body["latest_import"]["summary"] == {"nights": 3}
    assert body["latest_import"]["finished_at"].startswith("2026-11-10T08:00")


# ---- staleness (no automatic sync yet: an export ages) ----

OLD = TODAY - dt.timedelta(days=40)


def _old_snapshot(session):
    """An export taken 40 days ago: 20 days of heart and steps history ending on OLD, plus OLD's night."""
    for i in range(20):
        night = dict(sleep_total_min=420.0, sleep_deep_min=70, sleep_rem_min=90, sleep_light_min=240,
                     sleep_awake_min=20) if i == 0 else {}
        _daily(session, OLD - dt.timedelta(days=i), resting_hr=50.0 + i % 5, steps=8000.0 + i * 10, **night)
    _part(session, OLD, (23, 0), (7, 0), "old")
    session.commit()


def test_overview_of_a_40_day_old_export_is_stale_but_shows_its_values(client, session):
    _old_snapshot(session)
    body = client.get("/api/v1/signals/overview").json()
    assert body["stale"] is True and body["as_of"] == OLD.isoformat() and body["today"] == TODAY.isoformat()
    hr = _tile(body, "resting_hr")
    assert hr["value"] == 50.0 and hr["date"] == OLD.isoformat() and hr["band"] is not None and hr["position"] == "below"
    assert len(hr["spark"]) == 20 and hr["partial"] is False
    sleep = _tile(body, "sleep_total_min")
    assert sleep["value"] == 420 and sleep["date"] == OLD.isoformat()
    steps = _tile(body, "steps")
    assert steps["value"] == 8000 and steps["date"] == OLD.isoformat()
    assert steps["partial"] is True and steps["position"] is None  # the export's last day is cut off mid-day
    assert body["last_night"]["wake_date"] == OLD.isoformat() and body["has_data"] is True


def test_stale_tiles_end_on_as_of_but_a_newer_weight_still_shows(client, session):
    _old_snapshot(session)
    session.add(DailyMetric(metric_date=TODAY - dt.timedelta(days=1), resting_hr=99, steps=1, source="demo"))
    session.add(BodyMeasurement(measured_on=TODAY - dt.timedelta(days=2), kind="weight", value=80.5, source="manual"))
    session.commit()
    body = client.get("/api/v1/signals/overview").json()
    hr = _tile(body, "resting_hr")
    assert hr["value"] == 50.0 and hr["spark"][-1]["date"] == OLD.isoformat()
    assert _tile(body, "weight")["value"] == 80.5
    assert _tile(body, "steps")["partial"] is True  # the demo row after it is not the snapshot's newest day


def test_overview_of_a_fresh_export_is_not_stale(client, session):
    _hr_history(session, 12)
    session.get(DailyMetric, TODAY - dt.timedelta(days=1)).steps = 9000
    session.commit()
    body = client.get("/api/v1/signals/overview").json()
    assert body["stale"] is False and body["as_of"] == (TODAY - dt.timedelta(days=1)).isoformat()
    steps = _tile(body, "steps")
    assert steps["value"] == 9000 and steps["partial"] is False  # yesterday, fresh: a whole day


def test_empty_overview_has_no_as_of(client):
    body = client.get("/api/v1/signals/overview").json()
    assert body["as_of"] is None and body["stale"] is False


def test_todays_steps_are_partial_and_get_no_position(client, session):
    for i in range(1, 15):
        _daily(session, TODAY - dt.timedelta(days=i), steps=8000.0 + i)
    _daily(session, TODAY, steps=100.0)
    session.commit()
    steps = _tile(client.get("/api/v1/signals/overview").json(), "steps")
    assert steps["value"] == 100 and steps["band"] is not None
    assert steps["partial"] is True and steps["position"] is None
    series = client.get("/api/v1/signals/series?keys=steps,resting_hr").json()
    assert series["series"]["steps"]["partial"] is True and series["series"]["steps"]["position"] is None
    assert series["series"]["resting_hr"]["partial"] is False


def test_series_reports_staleness(client, session):
    _old_snapshot(session)
    body = client.get("/api/v1/signals/series?keys=steps,resting_hr").json()
    assert body["stale"] is True and body["as_of"] == OLD.isoformat() and body["today"] == TODAY.isoformat()
    assert body["series"]["steps"]["partial"] is True and body["series"]["steps"]["position"] is None
    assert body["series"]["resting_hr"]["position"] is not None and len(body["series"]["resting_hr"]["points"]) == 20


def test_stale_series_ends_on_as_of(client, session):
    _old_snapshot(session)
    session.add(DailyMetric(metric_date=TODAY - dt.timedelta(days=1), steps=1, source="demo"))
    session.add(BodyMeasurement(measured_on=TODAY - dt.timedelta(days=2), kind="weight", value=80.5, source="manual"))
    session.commit()
    body = client.get("/api/v1/signals/series?keys=steps,weight&from=2000-01-01").json()["series"]
    assert body["steps"]["points"][-1]["date"] == OLD.isoformat() and body["steps"]["partial"] is True
    assert body["weight"]["points"][-1]["value"] == 80.5


def test_sleep_split_is_anchored_on_as_of_when_stale(client, session):
    for i in range(0, 30):
        _daily(session, OLD - dt.timedelta(days=i), sleep_total_min=420.0)
    for i in range(30, 60):
        _daily(session, OLD - dt.timedelta(days=i), sleep_total_min=400.0)
    session.commit()
    body = client.get("/api/v1/signals/sleep").json()
    assert body["stale"] is True and body["as_of"] == OLD.isoformat() and body["today"] == TODAY.isoformat()
    s = body["summary"]
    assert s["last30"]["nights"] == 30 and s["last30"]["duration_min"] == 420
    assert s["prev30"]["nights"] == 30 and s["prev30"]["duration_min"] == 400


def test_sleep_split_uses_today_when_fresh(client, session):
    _daily(session, TODAY - dt.timedelta(days=3), sleep_total_min=420.0)
    _daily(session, TODAY - dt.timedelta(days=35), sleep_total_min=400.0)
    session.commit()
    body = client.get("/api/v1/signals/sleep").json()
    assert body["stale"] is False
    assert body["summary"]["last30"]["nights"] == 1 and body["summary"]["prev30"]["nights"] == 1


def test_demo_rows_do_not_count_as_data(client, session):
    session.add(DailyMetric(metric_date=TODAY - dt.timedelta(days=1), steps=5000, resting_hr=55, source="demo"))
    session.commit()
    body = client.get("/api/v1/signals/overview").json()
    assert body["has_data"] is False and body["as_of"] is None
    _daily(session, OLD, steps=7000.0)
    session.commit()
    body = client.get("/api/v1/signals/overview").json()
    assert body["has_data"] is True and body["as_of"] == OLD.isoformat()


def test_demo_owned_field_in_a_real_row_does_not_set_as_of(client, session):
    _daily(session, OLD, steps=7000.0)
    session.add(DailyMetric(metric_date=TODAY - dt.timedelta(days=1), resting_hr=55, stress_avg=20, source="health_sync",
                            field_sources={"resting_hr": "demo", "stress_avg": "health_sync"}))
    session.commit()
    assert client.get("/api/v1/signals/overview").json()["as_of"] == OLD.isoformat()


def test_latest_import_finished_at_carries_utc_offset(client, session):
    session.add(ImportJob(kind="samsung_health", status="done", progress=1, summary={},
                          finished_at=dt.datetime(2026, 11, 10, 23, 30, tzinfo=dt.UTC)))  # SQLite hands it back naive
    session.commit()
    assert client.get("/api/v1/signals/overview").json()["latest_import"]["finished_at"] == "2026-11-10T23:30:00+00:00"


# ---- series ----

def test_series_points_band_and_weight(client, session):
    _hr_history(session, 20)
    _daily(session, TODAY, resting_hr=60.0, steps=1000)
    session.add(BodyMeasurement(measured_on=TODAY, kind="weight", value=81.0, source="manual"))
    session.commit()
    frm = (TODAY - dt.timedelta(days=2)).isoformat()
    body = client.get(f"/api/v1/signals/series?keys=resting_hr,weight,steps&from={frm}&to={TODAY.isoformat()}").json()["series"]
    assert [p["date"] for p in body["resting_hr"]["points"]] == [(TODAY - dt.timedelta(days=d)).isoformat() for d in (2, 1, 0)]
    assert body["resting_hr"]["band"] is not None and body["resting_hr"]["name"] and body["resting_hr"]["unit"]
    assert body["weight"]["points"] == [{"date": TODAY.isoformat(), "value": 81.0}]
    assert body["weight"]["band"] is None
    assert body["steps"]["points"] == [{"date": TODAY.isoformat(), "value": 1000}]


def test_series_unknown_key_422_localized(client):
    res = client.get("/api/v1/signals/series?keys=resting_hr,bogus")
    assert res.status_code == 422 and "bogus" in res.json()["detail"]
    ru = client.get("/api/v1/signals/series?keys=bogus", headers={"Accept-Language": "ru"})
    assert ru.status_code == 422 and ru.json()["detail"] != res.json()["detail"]


def test_series_internal_fields_not_whitelisted(client):
    assert client.get("/api/v1/signals/series?keys=source").status_code == 422
    assert client.get("/api/v1/signals/series?keys=field_sources").status_code == 422


# ---- sleep ----

def test_sleep_nights_one_per_wake_date_with_local_times(client, session):
    wake = D(2026, 11, 5)
    _night_row(session, wake)
    _part(session, wake, (23, 0), (3, 0), "a", off=300)
    _part(session, wake, (3, 30), (7, 0), "b", off=300)
    _part(session, wake, (13, 0), (13, 40), "nap", off=300, main=False)
    _part(session, D(2026, 11, 6), (22, 0), (6, 0), "c", off=-240, duration_min=480)  # no DailyMetric: falls back to part
    session.commit()
    body = client.get("/api/v1/signals/sleep?from=2026-11-01&to=2026-11-12").json()
    nights = body["nights"]
    assert [n["wake_date"] for n in nights] == ["2026-11-06", "2026-11-05"]
    n5 = nights[1]
    assert n5["parts"] == 2 and n5["start_local"] == "2026-11-04T23:00:00" and n5["end_local"] == "2026-11-05T07:00:00"
    assert (n5["duration_min"], n5["deep"], n5["rem"], n5["light"], n5["awake"], n5["efficiency"]) == (420, 70, 90, 240, 20, 92)
    n6 = nights[0]
    assert n6["parts"] == 1 and n6["start_local"] == "2026-11-05T22:00:00" and n6["end_local"] == "2026-11-06T06:00:00"
    assert n6["duration_min"] == 480


def test_sleep_summary_last30_prev30(client, session):
    for i in range(0, 30):
        _daily(session, TODAY - dt.timedelta(days=i), sleep_total_min=420.0, sleep_deep_min=60.0)
    for i in range(30, 60):
        _daily(session, TODAY - dt.timedelta(days=i), sleep_total_min=400.0, sleep_deep_min=70.0)
    _daily(session, TODAY - dt.timedelta(days=61), sleep_total_min=1.0)
    session.commit()
    s = client.get("/api/v1/signals/sleep").json()["summary"]
    assert s["last30"]["duration_min"] == 420 and s["prev30"]["duration_min"] == 400
    assert s["change"]["duration_min"] == 20 and s["change"]["deep"] == -10
    assert s["last30"]["nights"] == 30
    assert s["last30"]["rem"] is None and s["change"]["rem"] is None


def test_sleep_detail_whole_night_and_404(client, session):
    wake = D(2026, 11, 5)
    _night_row(session, wake)
    a = _part(session, wake, (23, 0), (3, 0), "a", off=300)
    b = _part(session, wake, (3, 30), (7, 0), "b", off=300)
    t0 = a.start_utc
    session.add(SleepStage(session_id=a.id, external_id="1", start_utc=t0, end_utc=t0 + dt.timedelta(minutes=30), stage="light"))
    session.add(SleepStage(session_id=b.id, external_id="1", start_utc=b.start_utc, end_utc=b.start_utc + dt.timedelta(minutes=20), stage="deep"))
    session.commit()
    for pid in (a.id, b.id):
        body = client.get(f"/api/v1/signals/sleep/{pid}").json()
        assert body["session"]["parts"] == 2 and body["session"]["wake_date"] == "2026-11-05"
        assert body["session"]["duration_min"] == 420
        assert [(s["start_local"], s["stage"]) for s in body["stages"]] == [("2026-11-04T23:00:00", "light"), ("2026-11-05T03:30:00", "deep")]
    assert client.get("/api/v1/signals/sleep/9999").status_code == 404
    ru = client.get("/api/v1/signals/sleep/9999", headers={"Accept-Language": "ru"})
    assert ru.json()["detail"] != client.get("/api/v1/signals/sleep/9999").json()["detail"]


# ---- workouts ----

def _workout(session, i, code, day=TODAY, off=300, **kw):
    start = (dt.datetime(day.year, day.month, day.day, 8, 0) - dt.timedelta(minutes=off) + dt.timedelta(minutes=i)).replace(tzinfo=dt.UTC)
    session.add(Workout(source="samsung_export", external_id=f"w{i}", start_utc=start, end_utc=start + dt.timedelta(minutes=30),
                        tz_offset_min=off, local_date=day, type_code=code, duration_min=30, **kw))


def test_workouts_names_types_and_filter(client, session):
    for i, code in enumerate([1001, 1001, 1002, 11007, 10007, 15002, 15003, 15005, 0, 77777]):
        _workout(session, i, code, kcal=100.0 + i, hr_avg=120.0)
    session.commit()
    body = client.get("/api/v1/signals/workouts").json()
    names = {i["type_code"]: i["type_name"] for i in body["items"]}
    assert names[1001] == "Walking" and names[1002] == "Running" and names[11007] == "Cycling"
    assert names[77777] == "Workout (code 77777)"
    assert body["items"][0]["start_local"].endswith("T08:09:00")  # newest first, local via offset
    assert {t["type_code"]: t["count"] for t in body["types"]}[1001] == 2
    only = client.get("/api/v1/signals/workouts?type=1001").json()
    assert len(only["items"]) == 2 and len(only["types"]) == 9  # type list ignores the filter
    ru = client.get("/api/v1/signals/workouts?type=77777", headers={"Accept-Language": "ru"}).json()
    assert ru["items"][0]["type_name"] == "Тренировка (код 77777)"
    ru2 = client.get("/api/v1/signals/workouts?type=1002", headers={"Accept-Language": "ru"}).json()
    assert ru2["items"][0]["type_name"] == "Бег"


def test_workouts_date_range(client, session):
    _workout(session, 1, 1001, day=TODAY)
    _workout(session, 2, 1001, day=TODAY - dt.timedelta(days=100))
    session.commit()
    assert len(client.get("/api/v1/signals/workouts").json()["items"]) == 1
    assert len(client.get(f"/api/v1/signals/workouts?from={TODAY - dt.timedelta(days=120)}&to={TODAY}").json()["items"]) == 2


# ---- constant queries ----

def _seed_many(session, n):
    for i in range(n):
        wake = TODAY - dt.timedelta(days=i)
        _night_row(session, wake)
        _part(session, wake, (23, 0), (7, 0), f"s{i}")
        _workout(session, i, 1001, day=wake)
        session.add(BodyMeasurement(measured_on=wake, kind="weight", value=80 + i / 10, source="manual"))
    session.commit()


@pytest.mark.parametrize("url", [
    "/api/v1/signals/overview",
    "/api/v1/signals/sleep",
    "/api/v1/signals/series?keys=resting_hr,sleep_total_min,weight",
    "/api/v1/signals/workouts",
])
def test_constant_query_count(url, client, session, engine):
    _seed_many(session, 5)
    few = _count_queries(client, engine, url)
    _seed_many_more(session)
    many = _count_queries(client, engine, url)
    assert many == few


def _seed_many_more(session):
    for i in range(5, 60):
        wake = TODAY - dt.timedelta(days=i)
        _night_row(session, wake)
        _part(session, wake, (23, 0), (7, 0), f"s{i}")
        _workout(session, i, 1001, day=wake)
        session.add(BodyMeasurement(measured_on=wake, kind="weight", value=80 + i / 10, source="manual"))
    session.commit()
