import datetime as dt
import hashlib

import pytest
from sqlmodel import select

from config import settings
from db.models import Biomarker, LabReport
from main import app
from routers.lab_uploads import get_lab_parser_factory
from services.ai_provider import AiNotConfigured
from services.gemini_parser import LabParser
from tests.pdf_factory import text_pdf

PDF = b"%PDF-1.4 synthetic lab report"
PDF_HASH = hashlib.sha256(PDF).hexdigest()


class CountingClient:
    def __init__(self):
        self.calls = 0
        self.mime_types = []

    def generate_json(self, prompt, pdf_bytes, schema, mime_type="application/pdf"):
        self.calls += 1
        self.mime_types.append(mime_type)
        return {"test_date": "2025-06-15", "lab_name": "Demo Lab", "results": [
            {"name": "Vitamin D", "value": 28, "unit": "ng/mL", "ref_min": 30, "ref_max": 100, "result_text": None}]}


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return tmp_path


@pytest.fixture
def ai():
    ai_client = CountingClient()
    app.dependency_overrides[get_lab_parser_factory] = lambda: (lambda: LabParser(ai_client))
    yield ai_client
    app.dependency_overrides.pop(get_lab_parser_factory, None)


def _upload(client, content=PDF, name="r.pdf", ctype="application/pdf"):
    return client.post("/api/v1/labs/upload", files={"file": (name, content, ctype)})


def _body(**over):
    body = {"test_date": "2025-06-15", "lab_name": "Demo Lab", "file_hash": PDF_HASH, "rows": [
        {"name": "Vitamin D", "value": 28, "unit": "ng/ml", "ref_min": 30, "ref_max": 100, "result_text": None}]}
    return {**body, **over}


def test_upload_returns_draft_without_saving(client, engine, ai, data_dir):
    res = _upload(client)
    assert res.status_code == 200
    draft = res.json()
    assert draft["file_hash"] == PDF_HASH and draft["test_date"] == "2025-06-15"
    row = draft["rows"][0]
    assert row["marker_key"] == "vitamin_d_25_oh" and row["is_out_of_range"] is True
    assert (data_dir / "pdf" / f"{PDF_HASH}.pdf").read_bytes() == PDF
    assert client.get("/api/v1/biomarkers").json() == []  # nothing stored until confirmed


def test_upload_rejects_non_pdf_and_oversize(client, ai, monkeypatch):
    assert _upload(client, b"just text", "r.pdf").status_code == 415
    monkeypatch.setattr("routers.lab_uploads.MAX_UPLOAD_BYTES", 10)
    assert _upload(client, PDF).status_code == 413
    assert ai.calls == 0


def test_upload_without_ai_configured_returns_503_with_instructions(client, data_dir):
    def unavailable():
        raise AiNotConfigured("Add GEMINI_API_KEY to .env to enable this")
    app.dependency_overrides[get_lab_parser_factory] = lambda: unavailable
    try:
        res = _upload(client)
    finally:
        app.dependency_overrides.pop(get_lab_parser_factory, None)
    assert res.status_code == 503 and "Add GEMINI_API_KEY to .env to enable this" in res.json()["detail"]


def test_bad_model_output_returns_502(client, data_dir):
    class Garbage:
        def generate_json(self, *args):
            return {"results": "nope"}
    app.dependency_overrides[get_lab_parser_factory] = lambda: (lambda: LabParser(Garbage()))
    try:
        res = _upload(client)
    finally:
        app.dependency_overrides.pop(get_lab_parser_factory, None)
    assert res.status_code == 502 and "enter the results by hand" in res.json()["detail"]
    assert not (data_dir / "pdf").exists() or not list((data_dir / "pdf").iterdir())


def test_same_pdf_is_parsed_once_even_before_confirming(client, ai):
    first = _upload(client).json()
    second = _upload(client)
    assert second.status_code == 200 and second.json() == first and ai.calls == 1


def test_confirmed_pdf_returns_409_with_existing_report(client, ai):
    _upload(client)
    report_id = client.post("/api/v1/labs/confirm", json=_body()).json()["report_id"]
    res = _upload(client)
    assert res.status_code == 409 and res.json()["detail"]["report_id"] == report_id
    assert ai.calls == 1


def test_confirm_creates_report_and_biomarkers_and_is_idempotent(client, engine, ai):
    _upload(client)
    first = client.post("/api/v1/labs/confirm", json=_body())
    assert first.status_code == 201 and first.json()["created"] is True
    again = client.post("/api/v1/labs/confirm", json=_body())
    assert again.status_code == 200 and again.json()["created"] is False
    assert again.json()["report_id"] == first.json()["report_id"]
    assert first.json()["markers"] == [{"marker_key": "vitamin_d_25_oh", "display_name": "Vitamin D (25-OH)"}]
    from sqlmodel import Session
    with Session(engine) as s:
        rep = s.exec(select(LabReport)).one()
        bm = s.exec(select(Biomarker)).one()
    assert (rep.source, rep.external_id, rep.file_hash) == ("pdf", PDF_HASH, PDF_HASH)
    assert rep.pdf_path == f"pdf/{PDF_HASH}.pdf"
    assert (bm.source, bm.external_id, bm.unit, bm.is_out_of_range) == ("pdf", f"{PDF_HASH}#0", "ng/mL", True)


def test_confirm_requires_an_uploaded_file_and_a_date(client, ai):
    assert client.post("/api/v1/labs/confirm", json=_body()).status_code == 404  # never uploaded
    _upload(client)
    assert client.post("/api/v1/labs/confirm", json=_body(test_date=None)).status_code == 422
    assert client.post("/api/v1/labs/confirm", json=_body(file_hash="../../etc/passwd")).status_code == 422
    assert client.post("/api/v1/labs/confirm", json=_body(rows=[])).status_code == 422


def test_manual_entry_without_ai_feeds_history(client):
    for date, value in [("2022-01-10", 18), ("2023-02-10", 24), ("2025-03-10", 36)]:
        body = {"test_date": date, "lab_name": "", "rows": [
            {"name": "Vitamin D", "value": value, "unit": "ng/mL", "ref_min": 30, "ref_max": 100}]}
        res = client.post("/api/v1/labs/manual", json=body)
        assert res.status_code == 201
    h = client.get("/api/v1/biomarkers/vitamin_d_25_oh/history").json()
    assert [p["value"] for p in h["points"]] == [18, 24, 36]
    assert [p["out_of_range"] for p in h["points"]] == [True, True, False]
    assert [d["abs"] for d in h["deltas"]] == [6, 12]


def test_manual_row_validation(client):
    def post(rows):
        return client.post("/api/v1/labs/manual", json={"test_date": "2024-01-01", "rows": rows})
    assert post([{"name": "", "value": 1}]).status_code == 422
    assert post([{"name": "Ferritin"}]).status_code == 422  # neither value nor text
    assert post([{"name": "Ferritin", "value": 5, "ref_min": 9, "ref_max": 2}]).status_code == 422


def test_delete_removes_manual_and_pdf_reports_only(client, engine, ai, data_dir):
    _upload(client)
    pdf_id = client.post("/api/v1/labs/confirm", json=_body()).json()["report_id"]
    manual_id = client.post("/api/v1/labs/manual", json={"test_date": "2024-01-01", "rows": [
        {"name": "Ferritin", "value": 50}]}).json()["report_id"]
    from sqlmodel import Session
    with Session(engine) as s:
        imported = LabReport(test_date=dt.date(2020, 1, 1), source="notion", external_id="x")
        s.add(imported)
        s.commit()
        imported_id = imported.id
    assert client.delete(f"/api/v1/labs/{imported_id}").status_code == 403
    assert client.delete("/api/v1/labs/9999").status_code == 404
    assert client.delete(f"/api/v1/labs/{manual_id}").status_code == 204
    assert client.delete(f"/api/v1/labs/{pdf_id}").status_code == 204
    assert not (data_dir / "pdf" / f"{PDF_HASH}.pdf").exists()
    with Session(engine) as s:
        assert s.exec(select(Biomarker)).all() == []


def test_endpoints_require_token(client):
    from fastapi.testclient import TestClient
    anon = TestClient(app)
    assert anon.post("/api/v1/labs/manual", json={}).status_code == 401


def test_marker_name_catalog_lists_known_markers(client):
    names = client.get("/api/v1/labs/marker-names").json()
    assert "Vitamin D (25-OH)" in names and names == sorted(names, key=str.lower)


JPEG = b"\xff\xd8\xff\xe0 synthetic photo of a lab report"
PNG = b"\x89PNG\r\n\x1a\n synthetic scan"
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00 synthetic phone photo"


@pytest.mark.parametrize("content, name, ctype, mime, ext", [
    (JPEG, "p.jpg", "image/jpeg", "image/jpeg", ".jpg"),
    (PNG, "p.png", "image/png", "image/png", ".png"),
    (HEIC, "p.heic", "image/heic", "image/heic", ".heic"),
])
def test_photo_of_a_report_is_parsed_once_and_stored_with_its_own_type(client, ai, data_dir, content, name, ctype, mime, ext):
    file_hash = hashlib.sha256(content).hexdigest()
    res = _upload(client, content, name, ctype)
    assert res.status_code == 200 and res.json()["file_hash"] == file_hash
    assert ai.mime_types == [mime]
    assert (data_dir / "pdf" / f"{file_hash}{ext}").read_bytes() == content
    assert _upload(client, content, name, ctype).status_code == 200 and ai.calls == 1  # cached draft


def test_photo_confirm_saves_report_and_delete_removes_the_photo(client, engine, ai, data_dir):
    file_hash = hashlib.sha256(JPEG).hexdigest()
    _upload(client, JPEG, "p.jpg", "image/jpeg")
    res = client.post("/api/v1/labs/confirm", json=_body(file_hash=file_hash))
    assert res.status_code == 201
    stored = data_dir / "pdf" / f"{file_hash}.jpg"
    assert stored.exists()
    with __import__("sqlmodel").Session(engine) as s:
        report = s.exec(select(LabReport)).one()
        assert report.pdf_path == f"pdf/{file_hash}.jpg"
    assert client.delete(f"/api/v1/labs/{res.json()['report_id']}").status_code == 204
    assert not stored.exists()


def test_other_file_types_are_still_refused(client, ai):
    assert _upload(client, b"GIF89a...", "p.gif", "image/gif").status_code == 415
    assert ai.calls == 0


def test_pdf_with_a_text_layer_is_read_locally_without_the_ai(client, ai):
    pdf = text_pdf("Date 2025-03-04", "Test Result Reference Unit", "Ferritin 12 30-400 ng/ml")
    res = _upload(client, pdf)
    assert res.status_code == 200
    draft = res.json()
    assert ai.calls == 0 and draft["method"] == "text"
    row = draft["rows"][0]
    assert row["marker_key"] == "ferritin" and row["value"] == 12 and row["is_out_of_range"] is True


def test_pdf_whose_text_has_no_results_falls_back_to_the_ai(client, ai):
    res = _upload(client, text_pdf("Letter from the clinic with no numbers"))
    assert res.status_code == 200 and ai.calls == 1 and res.json()["method"] == "ai"
