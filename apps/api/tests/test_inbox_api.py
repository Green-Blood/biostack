import hashlib

import pytest
from sqlmodel import select

from config import settings
from db.models import Biomarker, LabReport, MedicalRecord, RecordAttachment
from tests.pdf_factory import blank_pdf, text_pdf

LAB = text_pdf("Date 2025-03-04", "Test Result Reference Unit", "Ferritin 12 30-400 ng/ml")
NOTE = text_pdf("MRI of the brain", "Impression: no focal changes")
LETTER = text_pdf("Letter from the clinic with no numbers")
JPEG = b"\xff\xd8\xff\xe0 synthetic photo"
ROW = {"name": "Ferritin", "value": 12, "unit": "ng/ml", "ref_min": 30, "ref_max": 400}


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return tmp_path


def _analyze(client, content, name="f.pdf", lang=None):
    headers = {"Accept-Language": lang} if lang else {}
    return client.post("/api/v1/inbox/analyze", files={"file": (name, content, "application/octet-stream")}, headers=headers)


def _confirm(client, items, lang=None):
    headers = {"Accept-Language": lang} if lang else {}
    res = client.post("/api/v1/inbox/confirm", json={"items": items}, headers=headers)
    assert res.status_code == 200
    return res.json()["results"]


def test_text_pdf_with_table_is_a_lab_read_locally(client):
    body = _analyze(client, LAB).json()
    assert body["kind"] == "lab" and body["needs_ai"] is False
    assert body["draft"]["method"] == "text" and body["draft"]["rows"][0]["marker_key"] == "ferritin"
    assert body["file_hash"] == hashlib.sha256(LAB).hexdigest()
    assert body["already_saved"] is None and body["suggested_record"] is None


def test_text_without_table_is_imaging_or_other(client):
    assert _analyze(client, NOTE).json()["kind"] == "imaging_report"
    other = _analyze(client, LETTER).json()
    assert other["kind"] == "other" and other["needs_ai"] is False and other["draft"] is None


def test_photo_and_scan_need_ai(client):
    for content in (JPEG, blank_pdf()):
        body = _analyze(client, content).json()
        assert body["kind"] == "other" and body["needs_ai"] is True and body["draft"] is None


def test_bad_type_is_rejected_localized(client):
    res = _analyze(client, b"plain text", lang="ru")
    assert res.status_code == 415 and "PDF" in res.json()["detail"]


def test_duplicate_upload_is_stable_and_saved_file_is_flagged(client):
    first = _analyze(client, LAB).json()
    assert _analyze(client, LAB).json() == first
    _confirm(client, [{"file_hash": first["file_hash"], "kind": "lab", "test_date": "2025-03-04", "rows": [ROW]}])
    again = _analyze(client, LAB).json()
    assert again["kind"] == "lab" and again["already_saved"]["report_id"]
    assert again["suggested_record"]["title"] == "Lab results 2025-03-04"


def test_suggested_record_is_nearest_within_14_days(client, session, monkeypatch):
    import datetime
    from routers import inbox as inbox_router
    real = inbox_router.parse_lab_text
    monkeypatch.setattr(inbox_router, "parse_lab_text",
                        lambda text, s=None: real(text, s).model_copy(update={"test_date": datetime.date(2025, 3, 4)}))
    near = MedicalRecord(title="Visit", record_date=__import__("datetime").date(2025, 3, 10))
    far = MedicalRecord(title="Old", record_date=__import__("datetime").date(2025, 1, 1))
    session.add(near); session.add(far); session.commit()
    assert _analyze(client, LAB).json()["suggested_record"]["title"] == "Visit"


def test_batch_confirm_mixed_good_and_bad(client, engine, session):
    lab = _analyze(client, LAB).json()["file_hash"]
    note = _analyze(client, NOTE, name="mri.pdf").json()["file_hash"]
    results = _confirm(client, [
        {"file_hash": lab, "kind": "lab", "test_date": "2025-03-04", "lab_name": "X", "rows": [ROW], "filename": "labs.pdf"},
        {"file_hash": note, "kind": "imaging_report", "filename": "mri.pdf"},
        {"file_hash": "0" * 64, "kind": "other"},
        {"file_hash": lab, "kind": "bogus"},
        {"file_hash": note, "kind": "lab", "rows": []},
    ])
    assert [r["status"] for r in results] == ["saved", "saved", "error", "error", "error"]
    assert all(r["message"] for r in results[2:])
    session.expire_all()
    lab_record = session.get(MedicalRecord, results[0]["record_id"])
    assert lab_record.record_type == "lab" and str(lab_record.record_date) == "2025-03-04"
    report = session.get(LabReport, results[0]["report_id"])
    assert report.record_id == lab_record.id and report.source == "pdf"
    assert len(session.exec(select(Biomarker).where(Biomarker.report_id == report.id)).all()) == 1
    attachments = session.exec(select(RecordAttachment)).all()
    assert {(a.record_id, a.filename) for a in attachments} == {(lab_record.id, "labs.pdf"), (results[1]["record_id"], "mri.pdf")}
    assert session.get(MedicalRecord, results[1]["record_id"]).record_type == "imaging"


def test_confirm_into_existing_record_and_already_saved(client, session):
    record = MedicalRecord(title="Visit"); session.add(record); session.commit(); session.refresh(record)
    h = _analyze(client, LAB).json()["file_hash"]
    item = {"file_hash": h, "kind": "lab", "test_date": "2025-03-04", "rows": [ROW], "record_id": record.id}
    assert _confirm(client, [item])[0]["record_id"] == record.id
    second = _confirm(client, [item])[0]
    assert second["status"] == "already_saved" and second["record_id"] == record.id
    assert len(session.exec(select(LabReport)).all()) == 1
    missing = _confirm(client, [{**item, "record_id": 999}])[0]
    assert missing["status"] == "error" and missing["record_id"] is None


def test_errors_are_localized(client):
    h = _analyze(client, LAB).json()["file_hash"]
    en = _confirm(client, [{"file_hash": h, "kind": "lab", "rows": [ROW]}])[0]["message"]
    ru = _confirm(client, [{"file_hash": h, "kind": "lab", "rows": [ROW]}], lang="ru")[0]["message"]
    assert en == "Enter the test date for these results." and ru == "Укажите дату сдачи анализов."
    bad_row = _confirm(client, [{"file_hash": h, "kind": "lab", "test_date": "2025-03-04", "rows": [{"name": " "}]}], lang="ru")[0]
    assert bad_row["status"] == "error" and "Некоторые" in bad_row["message"]


def test_untitled_ru_record_title(client, session):
    h = _analyze(client, LETTER).json()["file_hash"]
    r = _confirm(client, [{"file_hash": h, "kind": "other", "test_date": "2025-01-02"}], lang="ru")[0]
    assert session.get(MedicalRecord, r["record_id"]).title == "Документ 2025-01-02"


def test_photo_ai_draft_is_accepted_by_confirm(client, session):
    h = _analyze(client, JPEG, name="p.jpg").json()["file_hash"]
    r = _confirm(client, [{"file_hash": h, "kind": "lab", "test_date": "2025-03-04", "rows": [ROW]}])[0]
    assert r["status"] == "saved"
    assert session.exec(select(RecordAttachment)).one().mime_type == "image/jpeg"
