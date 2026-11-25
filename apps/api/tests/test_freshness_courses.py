import datetime as dt
import json

import pytest
from sqlmodel import delete

from db.models import AppSetting, Biomarker, BriefingCache, LabReport, Medication
from services import clock
from services.briefing import fallback_bullets, get_briefing
from services.briefing_writer import BriefingWriter
from services.clock import local_zone
from services.context_builder import build_context

TODAY = dt.date(2026, 6, 1)
ZONE = local_zone()
NOW = dt.datetime(2026, 6, 1, 12, 0, tzinfo=ZONE).astimezone(dt.timezone.utc)
RU = {"Accept-Language": "ru"}


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda zone=None: TODAY)


def _result(session, key, days_ago, value=30.0, name="Vitamin D (25-OH)", ref=(30.0, 100.0), source="manual", on=None):
    day = on or TODAY - dt.timedelta(days=days_ago)
    rep = LabReport(test_date=day, source=source)
    session.add(rep)
    session.commit()
    session.add(Biomarker(report_id=rep.id, marker_key=key, display_name=name, value=value, unit="ng/mL", ref_min=ref[0],
                          ref_max=ref[1], is_out_of_range=value < ref[0] or value > ref[1], source=source))
    session.commit()


def _item(client, key, **kw):
    return next(i for i in client.get("/api/v1/freshness", **kw).json()["items"] if i["marker_key"] == key)


def _vd_interval(client):
    return _item(client, "vitamin_d_25_oh")["retest_days"]


def test_statuses_and_thresholds(client, session):
    _result(session, "vitamin_d_25_oh", 0)
    interval = _vd_interval(client)
    for age, status in [(interval, "fresh"), (interval + 1, "due"), (int(interval * 1.5), "due"), (int(interval * 1.5) + 1, "overdue")]:
        session.exec(__import__("sqlmodel").delete(Biomarker)); session.exec(__import__("sqlmodel").delete(LabReport)); session.commit()
        _result(session, "vitamin_d_25_oh", age)
        item = _item(client, "vitamin_d_25_oh")
        assert item["status"] == status and item["age_days"] == age and item["due_in_days"] == interval - age
        assert item["interval_source"] == "default" and item["reason"] == "interval" and item["course_id"] is None
    assert client.get("/api/v1/freshness").json()["today"] == TODAY.isoformat()


def test_custom_override_and_removal(client, session):
    _result(session, "vitamin_d_25_oh", 40)
    default = _vd_interval(client)
    r = client.put("/api/v1/freshness/vitamin_d_25_oh/interval", json={"days": 20})
    assert r.status_code == 200
    body = r.json()
    assert body["retest_days"] == 20 and body["interval_source"] == "custom" and body["status"] == "overdue"
    assert session.get(AppSetting, "retest_days:vitamin_d_25_oh").value == {"days": 20}
    back = client.put("/api/v1/freshness/vitamin_d_25_oh/interval", json={"days": None}).json()
    assert back["retest_days"] == default and back["interval_source"] == "default"
    assert session.get(AppSetting, "retest_days:vitamin_d_25_oh") is None
    assert client.put("/api/v1/freshness/vitamin_d_25_oh/interval", json={"days": 0}).status_code == 422
    assert client.put("/api/v1/freshness/vitamin_d_25_oh/interval", json={"days": 3651}).status_code == 422


def test_unknown_marker_is_a_localized_404(client):
    assert client.put("/api/v1/freshness/nope/interval", json={"days": 5}).json()["detail"] == "Unknown marker"
    assert client.put("/api/v1/freshness/nope/interval", json={"days": 5}, headers=RU).status_code == 404


def test_markers_without_an_interval_are_fresh_with_null_retest(client, session):
    _result(session, "unmapped:xyz", 900, name="Xyz")
    item = _item(client, "unmapped:xyz")
    assert item["status"] == "fresh" and item["retest_days"] is None and item["due_in_days"] is None


def test_only_numeric_results_and_demo_is_dropped_when_real_exists(client, session):
    _result(session, "vitamin_d_25_oh", 5, source="demo")
    assert [i["marker_key"] for i in client.get("/api/v1/freshness").json()["items"]] == ["vitamin_d_25_oh"]
    _result(session, "ferritin", 5, name="Ferritin")
    assert [i["marker_key"] for i in client.get("/api/v1/freshness").json()["items"]] == ["ferritin"]


def test_sorting_overdue_first_then_due_then_fresh(client, session):
    _result(session, "vitamin_d_25_oh", 0)
    interval = _vd_interval(client)
    session.exec(delete(Biomarker)); session.exec(delete(LabReport)); session.commit()
    _result(session, "vitamin_d_25_oh", interval * 3)
    _result(session, "ferritin", 1, name="Ferritin")
    _result(session, "tsh", 10_000, name="TSH")
    order = [i["marker_key"] for i in client.get("/api/v1/freshness").json()["items"]]
    assert order[0] == "tsh" and order[-1] == "ferritin"


def test_finished_course_without_newer_result_forces_due(client, session):
    _result(session, "vitamin_d_25_oh", 0, on=dt.date(2026, 4, 20))
    assert _item(client, "vitamin_d_25_oh")["status"] == "fresh"
    c = client.post("/api/v1/courses", json={"name": "D3", "start_date": "2026-04-01", "days": 30, "target_marker_key": "vitamin_d_25_oh"}).json()
    item = _item(client, "vitamin_d_25_oh")
    assert item["status"] == "due" and item["reason"] == "course" and item["course_id"] == c["id"]
    _result(session, "vitamin_d_25_oh", 0, value=60, on=dt.date(2026, 5, 20))  # after the end date 2026-04-30
    assert _item(client, "vitamin_d_25_oh")["reason"] == "interval"


# ---- courses

def _course(client, **kw):
    body = {"name": "D3", "dosage": "2000 IU", "start_date": "2026-05-01", **kw}
    return client.post("/api/v1/courses", json=body)


def test_create_with_days_converts_to_end_date_and_status(client):
    c = _course(client, days=30, target_marker_key="vitamin_d_25_oh").json()
    assert c["end_date"] == "2026-05-30" and c["days"] == 30 and c["status"] == "finished" and c["ends_in_days"] is None
    assert c["source"] == "manual" and c["editable"] and c["target_marker_name"] == "Vitamin D (25-OH)"
    active = _course(client, start_date="2026-05-20", days=30).json()
    assert active["status"] == "active" and active["ends_in_days"] == 17
    planned = _course(client, start_date="2026-06-10").json()
    assert planned["status"] == "planned" and planned["end_date"] is None and planned["days"] is None


def test_course_validation(client):
    assert _course(client, days=5, end_date="2026-05-10").status_code == 422
    r = _course(client, end_date="2026-04-01")
    assert r.status_code == 422 and "end date" in r.json()["detail"]
    r = client.post("/api/v1/courses", json={"name": "D3", "start_date": "2026-05-01", "end_date": "2026-04-01"}, headers=RU)
    assert "даты" in r.json()["detail"].lower() or "дата" in r.json()["detail"].lower()
    assert _course(client, target_marker_key="nope").status_code == 422
    assert _course(client, name="  ").status_code == 422
    assert _course(client, days=0).status_code == 422


def test_list_newest_first(client):
    _course(client, name="old", start_date="2026-01-01")
    _course(client, name="new", start_date="2026-05-01")
    assert [c["name"] for c in client.get("/api/v1/courses").json()] == ["new", "old"]


def test_patch_and_delete_manual(client):
    cid = _course(client).json()["id"]
    r = client.patch(f"/api/v1/courses/{cid}", json={"days": 10, "name": "D3 forte"}).json()
    assert r["end_date"] == "2026-05-10" and r["name"] == "D3 forte"
    assert client.patch(f"/api/v1/courses/{cid}", json={"end_date": None}).json()["end_date"] is None
    assert client.patch(f"/api/v1/courses/{cid}", json={"end_date": "2026-01-01"}).status_code == 422
    assert client.delete(f"/api/v1/courses/{cid}").status_code == 204
    assert client.delete(f"/api/v1/courses/{cid}").status_code == 404
    assert client.patch("/api/v1/courses/999", json={}, headers=RU).status_code == 404


def test_imported_course_only_marker_and_notes_change(client, session):
    m = Medication(name="Imported", start_date=dt.date(2026, 5, 1), source="notion", external_id="x1")
    session.add(m)
    session.commit()
    row = client.get("/api/v1/courses").json()[0]
    assert row["editable"] is False and row["source"] == "notion"
    ok = client.patch(f"/api/v1/courses/{m.id}", json={"target_marker_key": "vitamin_d_25_oh", "notes": "hi"})
    assert ok.status_code == 200 and ok.json()["target_marker_key"] == "vitamin_d_25_oh" and ok.json()["notes"] == "hi"
    bad = client.patch(f"/api/v1/courses/{m.id}", json={"name": "x"})
    assert bad.status_code == 403 and bad.json()["detail"].startswith("This course was imported")
    assert client.patch(f"/api/v1/courses/{m.id}", json={"days": 3}, headers=RU).status_code == 403
    assert "импортирован" in client.delete(f"/api/v1/courses/{m.id}", headers=RU).json()["detail"]


# ---- effect

def _vd_course(client, **kw):
    return _course(client, start_date="2026-03-01", days=30, target_marker_key="vitamin_d_25_oh", **kw).json()["id"]


def test_effect_waiting_for_retest(client, session):
    _result(session, "vitamin_d_25_oh", 0, value=20, on=dt.date(2026, 2, 20))
    cid = _vd_course(client)
    e = client.get(f"/api/v1/courses/{cid}/effect").json()
    interval = _vd_interval(client)
    assert e["state"] == "waiting_for_retest" and e["after"] is None and e["before"]["value"] == 20
    assert e["retest_due_date"] == max(dt.date(2026, 3, 30), dt.date(2026, 3, 1) + dt.timedelta(days=interval)).isoformat()
    assert "not prove" in e["note"] and e["delta_abs"] is None


def test_effect_measured_toward_and_away(client, session):
    _result(session, "vitamin_d_25_oh", 0, value=20, on=dt.date(2026, 2, 20))
    _result(session, "vitamin_d_25_oh", 0, value=15, on=dt.date(2026, 3, 15))  # inside the course: not "after"
    _result(session, "vitamin_d_25_oh", 0, value=45, on=dt.date(2026, 4, 5))
    cid = _vd_course(client)
    e = client.get(f"/api/v1/courses/{cid}/effect").json()
    assert e["state"] == "measured" and e["after"] == {"date": "2026-04-05", "value": 45.0, "unit": "ng/mL"}
    assert e["delta_abs"] == 25 and e["delta_pct"] == 125 and e["toward_range"] is True and e["days_between"] == 44 and e["unit"] == "ng/mL"
    session.exec(__import__("sqlmodel").delete(Biomarker)); session.exec(__import__("sqlmodel").delete(LabReport)); session.commit()
    _result(session, "vitamin_d_25_oh", 0, value=40, on=dt.date(2026, 2, 20))
    _result(session, "vitamin_d_25_oh", 0, value=12, on=dt.date(2026, 4, 5))
    assert client.get(f"/api/v1/courses/{cid}/effect").json()["toward_range"] is False


def test_effect_no_baseline_when_missing_or_too_old(client, session):
    _result(session, "vitamin_d_25_oh", 0, value=45, on=dt.date(2026, 4, 5))
    cid = _vd_course(client)
    assert client.get(f"/api/v1/courses/{cid}/effect").json()["state"] == "no_baseline"
    interval = _vd_interval(client)
    _result(session, "vitamin_d_25_oh", 0, value=20, on=dt.date(2026, 3, 1) - dt.timedelta(days=2 * interval + 1))
    e = client.get(f"/api/v1/courses/{cid}/effect").json()
    assert e["state"] == "no_baseline" and e["before"] is None and e["delta_abs"] is None


def test_effect_marker_param_and_errors(client, session):
    _result(session, "ferritin", 0, value=50, name="Ferritin", on=dt.date(2026, 2, 20))
    cid = _course(client).json()["id"]  # no target
    assert client.get(f"/api/v1/courses/{cid}/effect").status_code == 422
    assert "Choose a marker" in client.get(f"/api/v1/courses/{cid}/effect").json()["detail"]
    assert "Выберите" in client.get(f"/api/v1/courses/{cid}/effect", headers=RU).json()["detail"]
    ok = client.get(f"/api/v1/courses/{cid}/effect", params={"marker": "ferritin"})
    assert ok.status_code == 200 and ok.json()["marker_key"] == "ferritin"
    assert client.get(f"/api/v1/courses/{cid}/effect", params={"marker": "zzz"}).status_code == 404
    assert client.get("/api/v1/courses/777/effect").status_code == 404


def test_effect_note_is_russian_for_ru(client, session):
    _result(session, "vitamin_d_25_oh", 0, on=dt.date(2026, 2, 20))
    cid = _vd_course(client)
    assert "не доказывает" in client.get(f"/api/v1/courses/{cid}/effect", headers=RU).json()["note"]


# ---- briefing honesty

def _ctx(session):
    return build_context(session, NOW, "23:00", ZONE)


def test_context_carries_data_age_and_labels_stale(session):
    _result(session, "vitamin_d_25_oh", 400, value=10)  # out of range, older than its interval
    _result(session, "ferritin", 5, value=5, name="Ferritin", ref=(30, 300))
    ctx = _ctx(session)
    stale = {m["name"]: m for m in ctx["out_of_range_biomarkers"]}
    assert stale["Vitamin D (25-OH)"]["stale"] is True and stale["Vitamin D (25-OH)"]["age_days"] == 400
    assert stale["Ferritin"]["stale"] is False
    assert {d["name"]: d["stale"] for d in ctx["data_age"]} == {"Vitamin D (25-OH)": True, "Ferritin": False}
    text = json.dumps(ctx)
    assert "journal" not in text and "description" not in text


def test_stale_bullet_in_both_languages(session):
    _result(session, "vitamin_d_25_oh", 400, value=10)
    ctx = _ctx(session)
    en = fallback_bullets(ctx, "en")
    ru = fallback_bullets(ctx, "ru")
    assert len(en) == 4 and "1 result is older than its suggested re-test interval" in en[3]
    assert "1 результат старше рекомендуемого срока пересдачи" in ru[3] and "пересдать" in ru[3]


def test_no_stale_bullet_when_fresh(session):
    _result(session, "ferritin", 5, value=5, name="Ferritin", ref=(30, 300))
    assert len(fallback_bullets(_ctx(session), "en")) == 3


def test_override_makes_a_result_stale(session):
    _result(session, "ferritin", 40, value=5, name="Ferritin", ref=(30, 300))
    assert _ctx(session)["data_age"][0]["stale"] is False
    session.add(AppSetting(key="retest_days:ferritin", value={"days": 10}))
    session.commit()
    assert _ctx(session)["data_age"][0]["stale"] is True


def test_course_bullets(session):
    session.add(Medication(name="D3", start_date=dt.date(2026, 4, 1), end_date=dt.date(2026, 5, 25), target_marker_key="vitamin_d_25_oh", source="manual"))
    session.add(Medication(name="Old", start_date=dt.date(2025, 1, 1), end_date=dt.date(2025, 2, 1), source="manual"))
    session.add(Medication(name="Iron", start_date=dt.date(2026, 5, 20), source="manual"))
    session.commit()
    ctx = _ctx(session)
    assert {c["name"] for c in ctx["courses"]} == {"D3", "Iron"}
    en = fallback_bullets(ctx, "en")[3:]
    assert "Course D3 ended on 2026-05-25: Vitamin D (25-OH) can be re-tested." in en
    ru = fallback_bullets(ctx, "ru")[3:]
    assert "Курс D3 закончился 2026-05-25: можно пересдать Витамин D (25-OH)." in " ".join(ru) or any("Курс D3 закончился 2026-05-25" in b for b in ru)


def test_cached_ai_briefing_is_not_served_after_data_age_changes(session):
    class Client:
        calls = 0

        def generate_json(self, prompt, document, schema, mime_type="application/pdf"):
            Client.calls += 1
            assert "stale" in prompt and b"journal" not in document
            return {"bullets": ["a", "b", "c"]}

    def go():
        return get_briefing(session, NOW, "23:00", ZONE, lambda: BriefingWriter(Client()), ai_enabled=True)

    go(); go()
    assert Client.calls == 1
    _result(session, "vitamin_d_25_oh", 400, value=10)  # data age changed
    go()
    assert Client.calls == 2
    # a cache row from before the stamp existed is ignored too
    for row in session.exec(__import__("sqlmodel").select(AppSetting)):
        if row.key.startswith("briefing_stamp:"):
            session.delete(row)
    session.commit()
    go()
    assert Client.calls == 3
    assert session.exec(__import__("sqlmodel").select(BriefingCache)).all()


def test_a_medicine_with_no_dates_is_undated_not_active(client, session):
    """Imported medicines often carry no dates; claiming they are running would be invented."""
    session.add(Medication(name="Imported, no dates", source="notion", external_id="n1"))
    session.add(Medication(name="Started, open-ended", start_date=TODAY - dt.timedelta(days=3), source="manual"))
    session.commit()
    by_name = {c["name"]: c for c in client.get("/api/v1/courses").json()}
    assert by_name["Imported, no dates"]["status"] == "undated"
    assert by_name["Started, open-ended"]["status"] == "active"


def test_undated_medicines_are_not_reported_as_running_courses(session):
    session.add(Medication(name="Imported, no dates", source="notion", external_id="n1"))
    session.commit()
    assert build_context(session, NOW, "23:00", ZONE)["courses"] == []
