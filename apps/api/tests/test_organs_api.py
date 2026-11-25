"""Organs read API: catalog, index, organ page data. All data is synthetic."""
import datetime as dt

import pytest
from sqlalchemy import event

from db.models import DateReview, MedicalRecord, Medication, RecordAttachment, RecordOrgan, ScanMeasurement
from services import organ_pages
from services.organs import ORGANS

D = dt.date


def _scan(session, date, title="Thyroid Ultrasound", organs=("thyroid",), rows=(), **kw):
    rec = MedicalRecord(record_type="imaging", title=title, record_date=date, **kw)
    session.add(rec)
    session.commit()
    session.refresh(rec)
    for o in organs:
        session.add(RecordOrgan(record_id=rec.id, organ_key=o))
    for r in rows:
        organ, param, side, val = r
        kind_text = isinstance(val, str)
        session.add(ScanMeasurement(record_id=rec.id, organ_key=organ, param_key=param, side=side,
                                    value=None if kind_text else val, value_text=val if kind_text else None,
                                    unit="" if kind_text else "x", origin="rule", verified=False))
    session.commit()
    return rec


def _vol(v):
    return ("thyroid", "volume_total", "", v)


def _get(client, key="thyroid", **kw):
    res = client.get(f"/api/v1/organs/{key}", **kw)
    assert res.status_code == 200, res.text
    return res.json()


def test_change_between_helper():
    assert organ_pages.change_between(10.0, 11.0) == {"delta": 1.0, "pct": 10.0, "direction": "up"}
    assert organ_pages.change_between(11.0, 10.0)["direction"] == "down"
    assert organ_pages.change_between(11.0, 11.0) == {"delta": 0.0, "pct": 0.0, "direction": "same"}
    assert organ_pages.change_between(0, 2.0) == {"delta": 2.0, "pct": None, "direction": "up"}
    assert organ_pages.change_between(3.0, 3.1234567)["delta"] == 0.1235
    assert organ_pages.change_between("Normal", "normal") == {"delta": None, "pct": None, "direction": "same"}
    assert organ_pages.change_between("normal", "increased") == {"delta": None, "pct": None, "direction": "changed"}


def test_detail_orders_scans_and_computes_changes(client, session):
    s3 = _scan(session, D(2025, 6, 1), rows=[_vol(11.0), ("thyroid", "nodule_max_mm", "", 4.0)])
    s1 = _scan(session, D(2022, 1, 15), rows=[_vol(10.0)])
    s2 = _scan(session, D(2023, 3, 1), rows=[_vol(11.0)])
    body = _get(client)
    assert [s["record_id"] for s in body["scans"]] == [s1.id, s2.id, s3.id]
    v = [s["values"]["volume_total"]["change"] for s in body["scans"]]
    assert v[0] is None
    assert v[1] == {"delta": 1.0, "pct": 10.0, "direction": "up"}
    assert v[2]["direction"] == "same"
    assert body["scans"][2]["values"]["nodule_max_mm"]["change"] is None
    assert body["scans"][2]["values"]["nodule_max_mm"]["origin"] == "rule"
    assert body["scans"][2]["has_numbers"] is True
    series = {s["series_key"]: s for s in body["series"]}
    assert len(series["volume_total"]["points"]) == 3
    assert series["volume_total"]["points"][0] == {"record_id": s1.id, "date": "2022-01-15", "value": 10.0}
    assert body["related_marker_keys"] == ["tsh", "free_t4", "free_t3", "anti_tpo"]
    assert body["aliases"] == ["thyroid", "щитовидн"]
    assert body["name"] == "Thyroid"
    assert {p["series_key"] for p in body["params"]} == {"volume_total", "nodule_max_mm"}
    p = next(p for p in body["params"] if p["series_key"] == "volume_total")
    assert p["param_key"] == "volume_total" and p["side"] == "" and p["chart"] is True and p["kind"] == "numeric"


def test_sided_series_key_and_catalog_order(client, session):
    _scan(session, D(2024, 1, 1), rows=[("thyroid", "volume_lobe", "right", 5.0), ("thyroid", "volume_total", "", 10.0),
                                         ("thyroid", "volume_lobe", "left", 4.0)])
    body = _get(client)
    assert [p["series_key"] for p in body["params"]] == ["volume_total", "volume_lobe:left", "volume_lobe:right"]
    assert "volume_lobe:right" in body["scans"][0]["values"]
    assert {s["series_key"] for s in body["series"]} == {"volume_total", "volume_lobe:left", "volume_lobe:right"}


def test_text_param_change(client, session):
    _scan(session, D(2023, 1, 1), rows=[("thyroid", "echogenicity", "", "normal")])
    _scan(session, D(2024, 1, 1), rows=[("thyroid", "echogenicity", "", "Normal")])
    _scan(session, D(2025, 1, 1), rows=[("thyroid", "echogenicity", "", "increased")])
    body = _get(client)
    ch = [s["values"]["echogenicity"]["change"] for s in body["scans"]]
    assert ch[0] is None
    assert ch[1] == {"delta": None, "pct": None, "direction": "same"}
    assert ch[2] == {"delta": None, "pct": None, "direction": "changed"}
    assert body["scans"][2]["values"]["echogenicity"]["value_text"] == "increased"
    assert body["series"] == []


def test_scan_without_numbers_still_listed_with_conclusion(client, session):
    rec = _scan(session, D(2024, 1, 1), details="Diffuse changes.", doctors_note="Repeat in a year.",
                body_markdown="# Report")
    scan = _get(client)["scans"][0]
    assert scan["record_id"] == rec.id and scan["has_numbers"] is False and scan["values"] == {}
    assert scan["details"] == "Diffuse changes." and scan["doctors_note"] == "Repeat in a year."
    assert scan["body_markdown"] == "# Report"
    assert scan["attachments"] == []


def test_attachments_listed(client, session):
    rec = _scan(session, D(2024, 1, 1))
    session.add(RecordAttachment(record_id=rec.id, filename="us.pdf", stored_path="x", mime_type="application/pdf",
                                 size_bytes=1, sha256="a"))
    session.commit()
    att = _get(client)["scans"][0]["attachments"]
    assert len(att) == 1 and att[0]["filename"] == "us.pdf" and att[0]["mime_type"] == "application/pdf"
    assert set(att[0]) == {"id", "filename", "mime_type"}


def test_multi_organ_scan_appears_on_each_tagged_organ_with_full_text(client, session):
    text = "Thyroid fine. Liver fine."
    rec = _scan(session, D(2024, 1, 1), title="Neck and abdomen", organs=("thyroid", "liver"), details=text)
    for key in ("thyroid", "liver"):
        scans = _get(client, key)["scans"]
        assert [s["record_id"] for s in scans] == [rec.id] and scans[0]["details"] == text


def test_same_date_scans_are_separate_columns_ordered_by_id(client, session):
    a = _scan(session, D(2024, 1, 1), rows=[_vol(10.0)])
    b = _scan(session, D(2024, 1, 1), rows=[_vol(12.0)])
    body = _get(client)
    assert [s["record_id"] for s in body["scans"]] == [a.id, b.id]
    assert [p["record_id"] for p in body["series"][0]["points"]] == [a.id, b.id]


def test_suspect_date_flagged_and_undated_last(client, session):
    sus = _scan(session, D(2024, 1, 1), date_suspect=True, rows=[_vol(10.0)])
    undated = _scan(session, None, rows=[_vol(99.0)])
    reviewed = _scan(session, D(2020, 1, 1), date_suspect=True, rows=[_vol(9.0)])
    session.add(DateReview(record_id=reviewed.id, confirmed_date=D(2025, 5, 5)))
    session.commit()
    body = _get(client)
    assert [s["record_id"] for s in body["scans"]] == [sus.id, reviewed.id, undated.id]
    by = {s["record_id"]: s for s in body["scans"]}
    assert by[sus.id]["date_suspect"] is True and by[sus.id]["date"] == "2024-01-01"
    assert by[reviewed.id]["date"] == "2025-05-05" and by[reviewed.id]["date_suspect"] is False
    assert by[undated.id]["date"] is None
    assert by[undated.id]["values"]["volume_total"]["value"] == 99.0  # still shown in the table
    assert [p["record_id"] for p in body["series"][0]["points"]] == [sus.id, reviewed.id]


def test_treatments_and_visits_in_range_with_related_flag(client, session):
    _scan(session, D(2023, 1, 1), rows=[_vol(10.0)])
    session.add_all([
        Medication(name="Levothyroxine", dosage="50 mcg", start_date=D(2023, 2, 1), target_marker_key="tsh"),
        Medication(name="Vitamin D", start_date=D(2023, 3, 1), end_date=D(2023, 4, 1)),
        Medication(name="Old course", start_date=D(2020, 1, 1), end_date=D(2022, 12, 31)),
    ])
    session.add_all([
        MedicalRecord(record_type="visit", title="Endocrinologist", record_date=D(2023, 6, 1)),
        MedicalRecord(record_type="visit", title="Too early", record_date=D(2022, 6, 1)),
        MedicalRecord(record_type="lab", title="Blood panel", record_date=D(2023, 6, 2)),
        MedicalRecord(record_type="imaging", title="Other scan", record_date=D(2023, 6, 3)),
    ])
    session.commit()
    body = _get(client)
    t = {x["name"]: x for x in body["treatments"]}
    assert set(t) == {"Levothyroxine", "Vitamin D"}
    assert t["Levothyroxine"]["related"] is True and t["Levothyroxine"]["end"] is None
    assert t["Levothyroxine"]["start"] == "2023-02-01" and t["Levothyroxine"]["dosage"] == "50 mcg"
    assert t["Vitamin D"]["related"] is False and t["Vitamin D"]["end"] == "2023-04-01"
    assert [v["title"] for v in body["visits"]] == ["Endocrinologist"]
    assert set(body["visits"][0]) == {"id", "date", "title", "record_type"}


def test_index_headline_unverified_and_unassigned(client, session):
    _scan(session, D(2023, 1, 1), rows=[_vol(10.0)])
    _scan(session, D(2024, 1, 1), rows=[_vol(11.0), ("thyroid", "nodule_count", "", 2.0)])
    session.add(ScanMeasurement(record_id=1, organ_key="thyroid", param_key="tirads", value=3.0, unit="score",
                                origin="manual", verified=True))
    liver = _scan(session, D(2025, 1, 1), title="Liver US", organs=("liver",))
    free = _scan(session, D(2024, 8, 8), title="Abdomen US", organs=())
    session.commit()
    body = client.get("/api/v1/organs").json()
    assert [o["key"] for o in body["organs"]] == ["liver", "thyroid"]  # newest latest_date first
    th = body["organs"][1]
    assert th["scan_count"] == 2 and th["latest_date"] == "2024-01-01" and th["unverified_count"] == 3
    assert th["name"] == "Thyroid"
    assert th["headline"] == {"series_key": "volume_total", "name": "Total volume", "unit": "cm³",
                              "value": 11.0, "previous": 10.0, "delta": 1.0, "pct": 10.0}
    assert body["organs"][0]["headline"] is None and body["organs"][0]["scan_count"] == 1
    assert body["unassigned"] == [{"record_id": free.id, "date": "2024-08-08", "title": "Abdomen US"}]
    assert liver.id not in [u["record_id"] for u in body["unassigned"]]


def test_index_headline_single_point_and_zero_previous(client, session):
    _scan(session, D(2023, 1, 1), organs=("spleen",), rows=[("spleen", "length_cm", "", 0.0)])
    assert client.get("/api/v1/organs").json()["organs"][0]["headline"]["pct"] is None
    _scan(session, D(2024, 1, 1), organs=("spleen",), rows=[("spleen", "length_cm", "", 11.0)])
    h = client.get("/api/v1/organs").json()["organs"][0]["headline"]
    assert h["previous"] == 0.0 and h["delta"] == 11.0 and h["pct"] is None
    _scan(session, D(2024, 1, 1), organs=("bladder",), rows=[("bladder", "volume_ml", "", 5.0)])
    b = next(o for o in client.get("/api/v1/organs").json()["organs"] if o["key"] == "bladder")
    assert b["headline"]["value"] == 5.0 and b["headline"]["previous"] is None
    assert b["headline"]["delta"] is None and b["headline"]["pct"] is None


def test_unknown_organ_404_and_empty_organ_200(client):
    assert client.get("/api/v1/organs/heart").status_code == 404
    ru = client.get("/api/v1/organs/heart", headers={"Accept-Language": "ru"})
    assert ru.json()["detail"] == "Орган не найден"
    body = _get(client, "liver")
    assert body["scans"] == [] and body["series"] == [] and body["params"] == []
    assert body["treatments"] == [] and body["visits"] == [] and body["key"] == "liver"
    assert client.get("/api/v1/organs").json() == {"organs": [], "unassigned": []}


def test_query_count_is_constant(client, session, engine):
    count = {"n": 0}

    def tick(*_a):
        count["n"] += 1

    def measure():
        count["n"] = 0
        event.listen(engine, "before_cursor_execute", tick)
        try:
            assert client.get("/api/v1/organs/thyroid").status_code == 200
            assert client.get("/api/v1/organs").status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", tick)
        return count["n"]

    def add(n, start):
        for i in range(n):
            rec = _scan(session, D(2020, 1, 1) + dt.timedelta(days=start + i), rows=[_vol(float(i)), ("thyroid", "echogenicity", "", "x")])
            session.add(RecordAttachment(record_id=rec.id, filename="f", stored_path="p", mime_type="image/png",
                                         size_bytes=1, sha256=str(rec.id)))
        session.commit()

    add(5, 0)
    few = measure()
    assert few > 0
    add(55, 10)
    assert measure() == few


def test_catalog_lists_all_organs_with_params(client):
    body = client.get("/api/v1/organs/catalog").json()
    assert [o["key"] for o in body] == list(ORGANS)
    th = body[0]
    assert th["name"] == "Thyroid"
    lobe = next(p for p in th["params"] if p["key"] == "volume_lobe")
    assert lobe == {"key": "volume_lobe", "name": "Lobe volume", "kind": "numeric", "unit": "cm³", "sides": True}
    ru = client.get("/api/v1/organs/catalog", headers={"Accept-Language": "ru"}).json()
    assert ru[0]["name"] == "Щитовидная железа"


def test_treatment_window_uses_configured_zone(client, session, monkeypatch):
    from services import app_settings, clock
    app_settings.save_settings(session, app_settings.load_settings(session).model_copy(update={"timezone": "Pacific/Kiritimati"}))
    _scan(session, D(2023, 1, 1), rows=[_vol(10.0)])
    session.add(Medication(name="Open", start_date=D(2023, 2, 1)))
    session.add(Medication(name="Tomorrow", start_date=D(2030, 1, 2)))
    session.commit()
    seen = []

    def fake_today(zone=None):
        seen.append(str(zone))
        return D(2030, 1, 2) if str(zone) == "Pacific/Kiritimati" else D(2030, 1, 1)

    monkeypatch.setattr(clock, "today", fake_today)
    names = {t["name"] for t in _get(client)["treatments"]}
    assert seen == ["Pacific/Kiritimati"] and names == {"Open", "Tomorrow"}


def test_unknown_side_does_not_break_detail(client, session):
    _scan(session, D(2024, 1, 1), rows=[("thyroid", "volume_lobe", "left", 4.0)])
    rec = session.exec(__import__("sqlmodel").select(MedicalRecord)).first()
    session.add(ScanMeasurement(record_id=rec.id, organ_key="thyroid", param_key="volume_lobe", side="bilateral",
                                value=9.0, unit="cm³"))
    session.commit()
    keys = [p["series_key"] for p in _get(client)["params"]]
    assert keys == ["volume_lobe:left", "volume_lobe:bilateral"]


def test_records_list_carries_organ_tags_in_constant_queries(client, session, engine):
    a = _scan(session, D(2024, 1, 1), title="Neck and abdomen", organs=("thyroid", "liver"))
    b = _scan(session, D(2024, 2, 1), title="Free scan", organs=())
    statements = []
    event.listen(engine, "before_cursor_execute", lambda *args: statements.append(args[2]))
    body = client.get("/api/v1/records", headers={"Accept-Language": "ru"}).json()
    by_id = {r["id"]: r for r in body}
    assert by_id[a.id]["organs"] == [{"key": "liver", "name": "Печень"}, {"key": "thyroid", "name": "Щитовидная железа"}]
    assert by_id[b.id]["organs"] == []
    statements.clear()
    client.get("/api/v1/records")
    before = len(statements)
    for i in range(5):
        _scan(session, D(2023, 1, 1 + i), organs=("kidneys",))
    statements.clear()
    client.get("/api/v1/records")
    assert len(statements) == before
