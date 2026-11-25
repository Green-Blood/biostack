import datetime as dt
import json
import subprocess
import sys

import pytest
from sqlmodel import Session, select

from config import settings
from db.models import (AppSetting, Diagnosis, MedicalRecord, Medication, RecordAttachment, RecordMedication, RecordNote)
from services import clock
from services.context_builder import build_context
from services.clock import local_zone

TODAY = dt.date(2026, 11, 11)
RU = {"Accept-Language": "ru"}
PDF = b"%PDF-1.4 synthetic discharge summary"
PNG = b"\x89PNG\r\n\x1a\n synthetic"


@pytest.fixture(autouse=True)
def pinned(monkeypatch, tmp_path):
    monkeypatch.setattr(clock, "today", lambda zone=None: TODAY)
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")


def make(client, **kw):
    body = {"record_type": "visit", "title": "Cardiology", **kw}
    r = client.post("/api/v1/records", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def imported(engine, **kw):
    with Session(engine) as s:
        rec = MedicalRecord(title="Imported", record_type="visit", record_date=dt.date(2024, 1, 5), source="notion",
                            external_id="n1", **kw)
        s.add(rec)
        s.commit()
        return rec.id


# create

def test_create_minimal_defaults_to_today_and_manual(client):
    rec = make(client)
    assert rec["date"] == "2026-11-11" and rec["is_manual"] is True and rec["status"] is None
    assert rec["end_date"] is None and rec["stay_days"] is None and rec["diagnoses"] == [] and rec["treatments"] == []
    assert rec["notes"] == [] and rec["attachments"] == [] and rec["department"] == ""


def test_create_full_payload(client, engine):
    rec = make(client, record_type="hospital_stay", title="Pneumonia", date="2026-11-02", clinic_name="City Hospital",
               department="Therapy", doctor_name="Dr. Ivanov", reason="Fever", details="d", doctors_note="n",
               diagnoses=[{"name": "Pneumonia", "icd10": "J18", "status": "confirmed", "note": "x"}, {"name": "Anemia"}],
               treatments=[{"name": "Ceftriaxone", "dosage": "1 g", "route": "IV", "frequency": "daily"}],
               questions=["When can I go home?"])
    assert rec["status"] == "ongoing" and rec["stay_days"] == 10 and rec["clinic"] == "City Hospital"
    assert [d["status"] for d in rec["diagnoses"]] == ["confirmed", "suspected"]
    t = rec["treatments"][0]
    assert t["route"] == "IV" and t["start_date"] == "2026-11-02" and t["status"] == "active" and t["editable"] is True
    assert rec["notes"] == [{"id": rec["notes"][0]["id"], "date": "2026-11-02", "text": "When can I go home?",
                             "kind": "question", "done": False}]
    with Session(engine) as s:
        med = s.exec(select(Medication)).one()
        assert med.source == "manual" and med.target_marker_key is None
        assert s.exec(select(MedicalRecord)).one().external_id is None


def test_clinic_not_duplicated(client, engine):
    make(client, clinic_name="City Hospital")
    make(client, clinic_name="CITY HOSPITAL")
    from db.models import Clinic
    with Session(engine) as s:
        assert len(s.exec(select(Clinic)).all()) == 1


@pytest.mark.parametrize("body,en,ru", [
    ({"record_type": "visit", "title": "  "}, "Give the record a title.", "Укажите название записи."),
    ({"record_type": "visit"}, "Give the record a title.", "Укажите название записи."),
    ({"record_type": "visit", "title": "x" * 201}, "longer than 200", "длиннее 200"),
    ({"record_type": "dentist", "title": "t"}, "Unknown record type.", "Неизвестный тип записи."),
    ({"title": "t"}, "Unknown record type.", "Неизвестный тип записи."),
    ({"record_type": "visit", "title": "t", "date": "2026-05-02", "end_date": "2026-05-01"}, "cannot be earlier", "раньше"),
    ({"record_type": "visit", "title": "t", "status": "weird"}, "Unknown status", "Неизвестный статус"),
    ({"record_type": "hospital_stay", "title": "t", "status": "completed"}, "needs an end date", "нужна дата окончания"),
    ({"record_type": "visit", "title": "t", "diagnoses": [{"name": " "}]}, "name", "название диагноза"),
    ({"record_type": "visit", "title": "t", "diagnoses": [{"name": "a", "status": "x"}]}, "suspected, confirmed", "предполагаемый"),
    ({"record_type": "visit", "title": "t", "treatments": [{"name": ""}]}, "name", "название лечения"),
])
def test_create_validation_en_and_ru(client, body, en, ru):
    r = client.post("/api/v1/records", json=body)
    assert r.status_code == 422 and en in r.json()["detail"]
    r = client.post("/api/v1/records", json=body, headers=RU)
    assert r.status_code == 422 and ru in r.json()["detail"]


def test_failed_create_leaves_nothing(client, engine):
    client.post("/api/v1/records", json={"record_type": "visit", "title": "t", "treatments": [{"name": "a"}, {"name": ""}]})
    with Session(engine) as s:
        assert not s.exec(select(MedicalRecord)).all() and not s.exec(select(Medication)).all()


def test_stay_status_and_days_with_pinned_clock(client):
    ongoing = make(client, record_type="hospital_stay", title="S", date="2026-11-02")
    assert ongoing["status"] == "ongoing" and ongoing["stay_days"] == 10
    done = make(client, record_type="hospital_stay", title="S2", date="2026-11-02", end_date="2026-11-05")
    assert done["status"] == "completed" and done["stay_days"] == 4
    same = make(client, record_type="hospital_stay", title="S3", date="2026-11-11")
    assert same["stay_days"] == 1
    items = {r["title"]: r for r in client.get("/api/v1/records").json()}
    assert items["S"]["stay_days"] == 10 and items["S2"]["end_date"] == "2026-11-05" and items["S"]["is_manual"] is True


def test_finish_stay(client):
    rec = make(client, record_type="hospital_stay", title="S", date="2026-11-02")
    r = client.post(f"/api/v1/records/{rec['id']}/finish", json={})
    assert r.json()["status"] == "completed" and r.json()["end_date"] == "2026-11-11" and r.json()["stay_days"] == 10
    r = client.post(f"/api/v1/records/{rec['id']}/finish", json={"end_date": "2026-11-08"})
    assert r.json()["end_date"] == "2026-11-08" and r.json()["stay_days"] == 7
    bad = client.post(f"/api/v1/records/{rec['id']}/finish", json={"end_date": "2026-11-01"}, headers=RU)
    assert bad.status_code == 422 and "раньше" in bad.json()["detail"]
    assert client.post("/api/v1/records/999/finish", json={}).status_code == 404


def test_finish_without_body(client):
    rec = make(client, record_type="hospital_stay", title="S", date="2026-11-02")
    assert client.post(f"/api/v1/records/{rec['id']}/finish").json()["status"] == "completed"


# patch

def test_patch_manual_record(client):
    rec = make(client, record_type="hospital_stay", title="S", date="2026-11-02")
    r = client.patch(f"/api/v1/records/{rec['id']}", json={"title": "New", "department": " ICU ", "end_date": "2026-11-06",
                                                           "clinic_name": "Hosp", "doctor_name": "Dr X", "reason": "r"})
    out = r.json()
    assert out["title"] == "New" and out["department"] == "ICU" and out["status"] == "completed" and out["stay_days"] == 5
    assert out["clinic"] == "Hosp" and out["doctor_name"] == "Dr X"
    r = client.patch(f"/api/v1/records/{rec['id']}", json={"end_date": None})
    assert r.json()["status"] == "ongoing" and r.json()["end_date"] is None
    assert client.patch(f"/api/v1/records/{rec['id']}", json={"date": "2026-11-20", "end_date": "2026-11-12"}).status_code == 422
    assert client.patch(f"/api/v1/records/{rec['id']}", json={"title": " "}, headers=RU).status_code == 422
    assert client.patch(f"/api/v1/records/{rec['id']}", json={"record_type": "nope"}).status_code == 422
    assert client.patch("/api/v1/records/999", json={}).status_code == 404


def test_imported_record_restrictions(client, engine):
    rid = imported(engine)
    r = client.patch(f"/api/v1/records/{rid}", json={"title": "Hacked"})
    assert r.status_code == 403 and "imported" in r.json()["detail"]
    r = client.patch(f"/api/v1/records/{rid}", json={"date": "2020-01-01"}, headers=RU)
    assert r.status_code == 403 and "импортирована" in r.json()["detail"]
    ok = client.patch(f"/api/v1/records/{rid}", json={"department": "Uro", "doctor_name": "Dr", "reason": "r",
                                                      "doctors_note": "n"})
    assert ok.status_code == 200 and ok.json()["department"] == "Uro" and ok.json()["is_manual"] is False
    assert client.patch(f"/api/v1/records/{rid}", json={"status": "completed", "end_date": "2024-01-07"}).status_code == 200
    d = client.delete(f"/api/v1/records/{rid}")
    assert d.status_code == 403
    assert client.delete(f"/api/v1/records/{rid}", headers=RU).json()["detail"].startswith("Эта запись импортирована")


def test_imported_record_accepts_children(client, engine):
    rid = imported(engine)
    assert client.post(f"/api/v1/records/{rid}/diagnoses", json={"name": "Cystitis"}).status_code == 201
    assert client.post(f"/api/v1/records/{rid}/notes", json={"text": "hi"}).status_code == 201
    assert client.post(f"/api/v1/records/{rid}/treatments", json={"name": "Drug"}).status_code == 201
    assert client.post(f"/api/v1/records/{rid}/attachments", files={"file": ("a.pdf", PDF)}).status_code == 201
    got = client.get(f"/api/v1/records/{rid}").json()
    assert got["treatments"][0]["start_date"] == "2024-01-05"


# delete

def test_delete_cascade_keeps_shared_treatment(client, engine):
    a = make(client, title="A", treatments=[{"name": "Solo"}, {"name": "Shared"}], diagnoses=[{"name": "D"}], questions=["q"])
    b = make(client, title="B")
    shared = next(t for t in a["treatments"] if t["name"] == "Shared")
    with Session(engine) as s:
        s.add(RecordMedication(record_id=b["id"], medication_id=shared["id"]))
        s.commit()
    client.post(f"/api/v1/records/{a['id']}/attachments", files={"file": ("a.pdf", PDF)})
    stored = next((settings.data_dir / "attachments").iterdir())
    assert client.delete(f"/api/v1/records/{a['id']}").status_code == 204
    with Session(engine) as s:
        assert [m.name for m in s.exec(select(Medication))] == ["Shared"]
        assert not s.exec(select(Diagnosis)).all() and not s.exec(select(RecordNote)).all()
        assert not s.exec(select(RecordAttachment)).all()
        assert [r.record_id for r in s.exec(select(RecordMedication))] == [b["id"]]
    assert stored.exists()
    assert client.get(f"/api/v1/records/{a['id']}").status_code == 404
    assert client.delete(f"/api/v1/records/{a['id']}").status_code == 404


# children

def test_diagnoses_crud(client):
    rec = make(client)
    d = client.post(f"/api/v1/records/{rec['id']}/diagnoses", json={"name": " Flu ", "icd10": "J10"})
    assert d.status_code == 201 and d.json()["name"] == "Flu" and d.json()["status"] == "suspected"
    did = d.json()["id"]
    p = client.patch(f"/api/v1/diagnoses/{did}", json={"status": "ruled_out", "note": "tests negative"})
    assert p.json()["status"] == "ruled_out" and p.json()["note"] == "tests negative" and p.json()["name"] == "Flu"
    assert client.patch(f"/api/v1/diagnoses/{did}", json={"status": "bad"}, headers=RU).status_code == 422
    assert client.patch(f"/api/v1/diagnoses/{did}", json={"name": ""}).status_code == 422
    assert client.post(f"/api/v1/records/{rec['id']}/diagnoses", json={"name": ""}, headers=RU).status_code == 422
    assert client.post("/api/v1/records/999/diagnoses", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/v1/diagnoses/{did}").status_code == 204
    assert client.delete(f"/api/v1/diagnoses/{did}", headers=RU).json()["detail"] == "Диагноз не найден"


def test_treatments_crud_and_status(client, engine):
    rec = make(client, date="2026-11-02")
    t = client.post(f"/api/v1/records/{rec['id']}/treatments", json={"name": "Drip", "route": "IV", "frequency": "bid",
                                                                    "start_date": "2026-11-20"})
    assert t.status_code == 201 and t.json()["status"] == "planned"
    tid = t.json()["id"]
    p = client.patch(f"/api/v1/treatments/{tid}", json={"start_date": "2026-11-03", "end_date": "2026-11-05", "dosage": "5 ml"})
    assert p.json()["status"] == "finished" and p.json()["dosage"] == "5 ml" and p.json()["route"] == "IV"
    assert client.patch(f"/api/v1/treatments/{tid}", json={"end_date": "2026-11-01"}).status_code == 422
    assert client.patch(f"/api/v1/treatments/{tid}", json={"name": " "}, headers=RU).status_code == 422
    with Session(engine) as s:
        s.add(Medication(name="Imported", source="notion", external_id="m"))
        s.commit()
        imp = s.exec(select(Medication).where(Medication.source == "notion")).one().id
    assert client.patch(f"/api/v1/treatments/{imp}", json={"dosage": "x"}).status_code == 403
    assert "импортировано" in client.delete(f"/api/v1/treatments/{imp}", headers=RU).json()["detail"]
    assert client.delete(f"/api/v1/treatments/{tid}").status_code == 204
    assert client.get(f"/api/v1/records/{rec['id']}").json()["treatments"] == []
    assert client.delete(f"/api/v1/treatments/{tid}").status_code == 404


def test_undated_treatment_stays_undated(client, engine):
    with Session(engine) as sess:
        rec = MedicalRecord(title="Old", source="notion", external_id="o1")  # no date at all
        sess.add(rec)
        sess.commit()
        rid = rec.id
    t = client.post(f"/api/v1/records/{rid}/treatments", json={"name": "Mystery"}).json()
    assert t["start_date"] is None and t["status"] == "undated"
    assert next(c for c in client.get("/api/v1/courses").json() if c["name"] == "Mystery")["status"] == "undated"


def test_notes_and_questions(client):
    rec = make(client, date="2026-11-01")
    rid = rec["id"]
    n1 = client.post(f"/api/v1/records/{rid}/notes", json={"text": "day 1", "date": "2026-11-01"}).json()
    n2 = client.post(f"/api/v1/records/{rid}/notes", json={"text": "day 2"}).json()
    q = client.post(f"/api/v1/records/{rid}/notes", json={"text": "Why?", "kind": "question"}).json()
    assert n2["date"] == "2026-11-11" and q["kind"] == "question" and q["done"] is False
    notes = client.get(f"/api/v1/records/{rid}").json()["notes"]
    assert [n["text"] for n in notes] == ["day 2", "day 1", "Why?"]
    p = client.patch(f"/api/v1/notes/{q['id']}", json={"done": True})
    assert p.json()["done"] is True
    assert client.patch(f"/api/v1/notes/{n1['id']}", json={"text": "edited", "date": "2026-11-03"}).json()["date"] == "2026-11-03"
    assert client.patch(f"/api/v1/notes/{n1['id']}", json={"text": " "}, headers=RU).status_code == 422
    assert client.post(f"/api/v1/records/{rid}/notes", json={"text": "x", "kind": "poem"}).status_code == 422
    assert client.post(f"/api/v1/records/{rid}/notes", json={"text": ""}, headers=RU).json()["detail"] == "Сначала напишите текст."
    assert client.delete(f"/api/v1/notes/{n1['id']}").status_code == 204
    assert client.delete(f"/api/v1/notes/{n1['id']}").status_code == 404


# files

def test_upload_and_delete_attachment(client, engine):
    rec = make(client)
    r = client.post(f"/api/v1/records/{rec['id']}/attachments", files={"file": ("../dir/summary.pdf", PDF)})
    assert r.status_code == 201
    body = r.json()
    assert body["filename"] == "summary.pdf" and body["mime_type"] == "application/pdf" and body["is_image"] is False
    assert body["size_bytes"] == len(PDF) and set(body) == {"id", "filename", "mime_type", "size_bytes", "is_image"}
    png = client.post(f"/api/v1/records/{rec['id']}/attachments", files={"file": ("p.png", PNG)}).json()
    assert png["is_image"] is True
    assert client.get(f"/api/v1/records/{rec['id']}").json()["attachment_count"] == 2
    assert client.delete(f"/api/v1/attachments/{body['id']}").status_code == 204
    assert len(list((settings.data_dir / "attachments").iterdir())) == 2  # stored files stay
    assert client.delete(f"/api/v1/attachments/{body['id']}").status_code == 404


def test_upload_rejects_wrong_type_and_big_files(client, monkeypatch):
    rec = make(client)
    r = client.post(f"/api/v1/records/{rec['id']}/attachments", files={"file": ("a.txt", b"hello")})
    assert r.status_code == 415 and "PDF" in r.json()["detail"]
    r = client.post(f"/api/v1/records/{rec['id']}/attachments", files={"file": ("a.txt", b"hello")}, headers=RU)
    assert r.status_code == 415 and "Прикрепите" in r.json()["detail"]
    from routers import record_items
    monkeypatch.setattr(record_items, "MAX_ATTACHMENT_BYTES", 10)
    r = client.post(f"/api/v1/records/{rec['id']}/attachments", files={"file": ("a.pdf", PDF)})
    assert r.status_code == 413
    r = client.post(f"/api/v1/records/{rec['id']}/attachments", files={"file": ("a.pdf", PDF)}, headers=RU)
    assert r.status_code == 413 and "МБ" in r.json()["detail"]
    assert client.post("/api/v1/records/999/attachments", files={"file": ("a.pdf", PDF)}).status_code == 404


# courses and search

def test_treatments_appear_in_courses(client):
    make(client, date="2026-11-02", treatments=[{"name": "Drip", "end_date": "2026-11-20"}])
    courses = client.get("/api/v1/courses").json()
    c = next(c for c in courses if c["name"] == "Drip")
    assert c["start_date"] == "2026-11-02" and c["status"] == "active" and c["target_marker_key"] is None


def test_search_by_diagnosis_department_doctor_reason_and_note(client):
    rec = make(client, title="Stay", department="Кардиология", doctor_name="Иванов", reason="Одышка",
               diagnoses=[{"name": "Пневмония", "icd10": "J18"}])
    client.post(f"/api/v1/records/{rec['id']}/notes", json={"text": "ночью была температура"})

    def hit(q, lang="en"):
        groups = client.get("/api/v1/search", params={"q": q}, headers={"Accept-Language": lang}).json()["groups"]
        recs = [g for g in groups if g["kind"] == "record"]
        return recs[0]["hits"][0] if recs else None

    h = hit("пневмония", "ru")
    assert h["href"] == f"/records/{rec['id']}" and h["subtitle"].startswith("Диагноз: ")
    assert hit("j18")["subtitle"].startswith("Diagnosis: ")
    assert hit("кардиология", "ru")["subtitle"].startswith("Отделение: ")
    assert hit("иванов", "ru")["subtitle"].startswith("Врач: ")
    assert hit("одышка", "ru")["subtitle"].startswith("Причина: ")
    assert hit("температура", "ru")["subtitle"].startswith("Заметка: ")
    assert hit("температура")["subtitle"].startswith("Note: ")
    assert hit("nothingmatches") is None


# privacy

SECRETS = ["Pneumoniaxyz", "Cardiologyxyz", "Drivanovxyz", "Fever-reasonxyz", "Whenhomexyz", "Nightnotexyz"]


def test_briefing_includes_visit_treatments_but_not_other_visit_details(client, engine):
    make(client, record_type="hospital_stay", title="Stay", date="2026-11-02", department="Cardiologyxyz",
         doctor_name="Drivanovxyz", reason="Fever-reasonxyz", diagnoses=[{"name": "Pneumoniaxyz", "icd10": "J18"}],
         treatments=[{"name": "Ceftriaxonexyz", "dosage": "1 g", "route": "IV"},
                     {"name": "Futurexyz", "start_date": "2026-12-01"}], questions=["Whenhomexyz"])
    client.post("/api/v1/records/1/notes", json={"text": "Nightnotexyz"})
    with Session(engine) as s:
        s.add(Medication(name="Ordinary course", start_date=dt.date(2026, 11, 1), source="manual"))
        s.commit()
        zone = local_zone()
        ctx = build_context(s, dt.datetime(2026, 11, 11, 12, 0, tzinfo=zone), "23:00", zone)
        blob = json.dumps(ctx, ensure_ascii=False, default=str)
        for secret in SECRETS:
            assert secret not in blob
        assert "Ceftriaxonexyz" in blob
        assert "Futurexyz" not in blob  # planned treatments are not active
        assert "Ordinary course" in blob  # courses made in the Courses page are still shared
        from services.chat import record_context
        chat = record_context(s, dt.date(2026, 11, 11))
        assert "Ceftriaxonexyz" in chat and "1 g" in chat and "Futurexyz" in chat
        from services.briefing import _stamp
        assert not any(x in json.dumps(_stamp(ctx), default=str) for x in SECRETS)
        stamps = [r.value for r in s.exec(select(AppSetting)) if r.key.startswith("briefing_stamp")]
        assert not any(x in v for v in stamps for x in SECRETS)


def test_request_bodies_are_not_logged(client, caplog):
    import logging
    with caplog.at_level(logging.DEBUG):
        make(client, title="Secretlogtitlexyz", reason="Secretlogreasonxyz")
    assert "Secretlog" not in caplog.text


# migration

def test_alembic_head_matches_models(tmp_path):
    import os
    from pathlib import Path
    api = Path(__file__).resolve().parents[1]
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'm.db'}"}
    for args in (["upgrade", "head"], ["check"]):
        r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=api, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
