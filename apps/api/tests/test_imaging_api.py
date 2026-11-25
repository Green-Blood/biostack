import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from config import settings
from db.models import ImagingStudy
from main import app
from routers.imaging import get_report_reader_factory
from services.ai_provider import AiNotConfigured
from services.report_reader import ReportReader
from tests.dicom_factory import corrupt_member, dicom_bytes, make_zip, mark_encrypted, series_members


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    return tmp_path / "data"


def _zip_bytes(tmp_path, members=None, name="study.zip") -> bytes:
    return make_zip(tmp_path / name, series_members(8) if members is None else members).read_bytes()


def _upload(client, content: bytes, **fields):
    return client.post("/api/v1/imaging/upload", files={"file": ("scan.zip", content, "application/zip")}, data=fields)


@pytest.fixture
def study(client, tmp_path):
    return _upload(client, _zip_bytes(tmp_path)).json()


def test_upload_extracts_keyframes_and_fills_metadata_from_dicom_tags(client, tmp_path, data_dir):
    content = _zip_bytes(tmp_path)
    res = _upload(client, content)
    assert res.status_code == 201
    body = res.json()
    assert (body["study_type"], body["body_part"], body["study_date"]) == ("CT", "CHEST", "2024-03-15")
    assert (body["slice_count"], body["frame_count"], body["series_description"]) == (8, 5, "Axial")
    folder = data_dir / "imaging" / hashlib.sha256(content).hexdigest()
    assert (folder / "study.zip").read_bytes() == content
    assert sorted(p.name for p in folder.glob("*.png")) == [f"frame_0{i}.png" for i in range(1, 6)]
    assert body["warnings"] == [] and not list((data_dir / "imaging").glob("*.part"))


def test_form_fields_override_dicom_tags(client, tmp_path):
    body = _upload(client, _zip_bytes(tmp_path), study_type="MRI", body_part="Lumbar spine", study_date="2023-01-02").json()
    assert (body["study_type"], body["body_part"], body["study_date"]) == ("MRI", "Lumbar spine", "2023-01-02")


def test_blank_form_fields_fall_back_to_dicom_tags(client, tmp_path):
    body = _upload(client, _zip_bytes(tmp_path), study_type="", body_part="", study_date="").json()
    assert (body["study_type"], body["study_date"]) == ("CT", "2024-03-15")


def test_study_date_is_required_when_the_archive_has_none(client, tmp_path, data_dir):
    content = _zip_bytes(tmp_path, {"a.dcm": dicom_bytes(study_date=None)})
    res = _upload(client, content)
    assert res.status_code == 422 and "study date" in res.json()["detail"]
    assert not (data_dir / "imaging" / hashlib.sha256(content).hexdigest()).exists()
    assert _upload(client, content, study_date="2022-05-06").status_code == 201


def test_same_archive_is_stored_once(client, tmp_path):
    content = _zip_bytes(tmp_path)
    first = _upload(client, content).json()
    again = _upload(client, content)
    assert again.status_code == 409 and again.json()["detail"]["study_id"] == first["id"]
    assert len(client.get("/api/v1/imaging").json()) == 1


@pytest.mark.parametrize("members", [
    {"../evil.dcm": dicom_bytes()},
    {"notes.txt": b"just text"},
    {},
])
def test_unusable_archives_are_rejected_without_leftovers(client, tmp_path, data_dir, members):
    res = _upload(client, _zip_bytes(tmp_path, members))
    assert res.status_code == 422 and isinstance(res.json()["detail"], str)
    assert list((data_dir / "imaging").iterdir()) == []


def test_file_that_is_not_a_zip_returns_422(client):
    res = _upload(client, b"this is not a zip")
    assert res.status_code == 422 and "not a valid ZIP" in res.json()["detail"]


def test_oversize_upload_returns_413(client, tmp_path, monkeypatch):
    monkeypatch.setattr("routers.imaging.MAX_ZIP_BYTES", 100)
    res = _upload(client, _zip_bytes(tmp_path))
    assert res.status_code == 413 and "smaller" in res.json()["detail"]


def test_list_is_newest_first_and_detail_matches(client, tmp_path):
    old = _upload(client, _zip_bytes(tmp_path, series_members(3), "a.zip"), study_date="2021-01-01").json()
    new = _upload(client, _zip_bytes(tmp_path, series_members(4), "b.zip"), study_date="2025-01-01").json()
    listing = client.get("/api/v1/imaging").json()
    assert [s["id"] for s in listing] == [new["id"], old["id"]]
    assert client.get(f"/api/v1/imaging/{old['id']}").json()["frame_count"] == 3
    assert client.get("/api/v1/imaging/999").status_code == 404


def test_frame_endpoint_serves_png(client, study):
    res = client.get(f"/api/v1/imaging/{study['id']}/frames/0")
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    assert res.content.startswith(b"\x89PNG")
    assert client.get(f"/api/v1/imaging/{study['id']}/frames/5").status_code == 404
    assert client.get(f"/api/v1/imaging/{study['id']}/frames/-1").status_code == 404
    assert client.get(f"/api/v1/imaging/{study['id']}/frames/abc").status_code == 422
    assert client.get("/api/v1/imaging/999/frames/0").status_code == 404


def test_frame_endpoint_never_serves_files_outside_the_data_dir(client, engine, study, data_dir):
    (data_dir.parent / "secret.png").write_bytes(b"secret")
    with Session(engine) as s:
        row = s.get(ImagingStudy, study["id"])
        row.keyframe_paths = ["../secret.png", "/etc/hosts"]
        s.add(row)
        s.commit()
    assert client.get(f"/api/v1/imaging/{study['id']}/frames/0").status_code == 404
    assert client.get(f"/api/v1/imaging/{study['id']}/frames/1").status_code == 404


def test_endpoints_require_the_token(client, study):
    anon = TestClient(app)
    assert anon.get("/api/v1/imaging").status_code == 401
    assert anon.get(f"/api/v1/imaging/{study['id']}/frames/0").status_code == 401
    assert anon.post("/api/v1/imaging/upload", files={"file": ("a.zip", b"x")}).status_code == 401
    assert anon.delete(f"/api/v1/imaging/{study['id']}").status_code == 401


def test_patch_edits_text_and_details_only_where_sent(client, study):
    res = client.patch(f"/api/v1/imaging/{study['id']}", json={"summary_text": "No acute findings.",
                                                               "findings_text": "Liver normal\nKidneys normal"})
    assert res.status_code == 200
    body = client.get(f"/api/v1/imaging/{study['id']}").json()
    assert body["summary_text"] == "No acute findings." and body["findings_text"] == "Liver normal\nKidneys normal"
    assert body["study_type"] == "CT"
    client.patch(f"/api/v1/imaging/{study['id']}", json={"study_date": "2024-04-01", "body_part": "Abdomen"})
    again = client.get(f"/api/v1/imaging/{study['id']}").json()
    assert (again["study_date"], again["body_part"], again["summary_text"]) == ("2024-04-01", "Abdomen", "No acute findings.")
    assert client.patch(f"/api/v1/imaging/{study['id']}", json={"study_date": "not a date"}).status_code == 422
    assert client.patch("/api/v1/imaging/999", json={}).status_code == 404


def test_delete_removes_row_and_files(client, study, data_dir):
    folder = next((data_dir / "imaging").iterdir())
    assert client.delete(f"/api/v1/imaging/{study['id']}").status_code == 204
    assert not folder.exists() and client.get(f"/api/v1/imaging/{study['id']}").status_code == 404
    assert client.delete(f"/api/v1/imaging/{study['id']}").status_code == 404


class FakeReportClient:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def generate_json(self, prompt, document, schema, mime_type="application/pdf"):
        self.calls.append(mime_type)
        return self.answer


def _with_reader(client_obj):
    app.dependency_overrides[get_report_reader_factory] = lambda: (lambda: ReportReader(client_obj))


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_report_reader_factory, None)


def _report(client, study_id, content=b"%PDF-1.4 report", name="report.pdf"):
    return client.post(f"/api/v1/imaging/{study_id}/report", files={"file": (name, content)})


def test_report_text_is_returned_as_a_draft_and_not_saved(client, study):
    ai = FakeReportClient({"summary": "Normal chest CT.", "findings": ["Lungs clear", "No effusion"]})
    _with_reader(ai)
    res = _report(client, study["id"])
    assert res.status_code == 200
    assert res.json() == {"summary_text": "Normal chest CT.", "findings_text": "Lungs clear\nNo effusion"}
    assert ai.calls == ["application/pdf"]
    assert client.get(f"/api/v1/imaging/{study['id']}").json()["summary_text"] == ""


def test_report_images_are_sent_with_their_own_type(client, study):
    ai = FakeReportClient({"summary": None, "findings": []})
    _with_reader(ai)
    assert _report(client, study["id"], b"\x89PNG\r\n\x1a\n....", "scan.png").status_code == 200
    assert _report(client, study["id"], b"\xff\xd8\xff\xe0....", "scan.jpg").status_code == 200
    assert ai.calls == ["image/png", "image/jpeg"]


def test_report_rejects_other_file_types_and_unknown_studies(client, study):
    ai = FakeReportClient({"summary": "x", "findings": []})
    _with_reader(ai)
    assert _report(client, study["id"], b"PK\x03\x04zip", "x.zip").status_code == 415
    assert _report(client, 999).status_code == 404
    assert ai.calls == []


def test_report_without_ai_configured_returns_503_with_instructions(client, study):
    def unavailable():
        raise AiNotConfigured("Add GEMINI_API_KEY to .env to enable this. You can still type the report in.")
    app.dependency_overrides[get_report_reader_factory] = lambda: unavailable
    res = _report(client, study["id"])
    assert res.status_code == 503 and "Add GEMINI_API_KEY to .env to enable this" in res.json()["detail"]


def test_report_with_garbled_model_output_returns_502(client, study):
    _with_reader(FakeReportClient({"summary": ["not", "text"]}))
    res = _report(client, study["id"])
    assert res.status_code == 502 and "type the report in" in res.json()["detail"]


def test_the_same_report_file_is_sent_to_the_ai_only_once(client, study, data_dir):
    ai = FakeReportClient({"summary": "No acute findings.", "findings": ["Clear lungs"]})
    _with_reader(ai)
    first = _report(client, study["id"])
    second = _report(client, study["id"])
    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert len(ai.calls) == 1
    stored = list((data_dir / "imaging" / "reports").iterdir())
    assert len(stored) == 2 and any(p.name.endswith(".draft.json") for p in stored)


def test_a_different_report_file_still_goes_to_the_ai(client, study):
    ai = FakeReportClient({"summary": "x", "findings": []})
    _with_reader(ai)
    _report(client, study["id"], b"%PDF-1.4 one")
    _report(client, study["id"], b"%PDF-1.4 two")
    assert len(ai.calls) == 2


@pytest.mark.parametrize("damage", ["corrupt", "encrypted"])
def test_unusable_archives_return_422_and_leave_nothing_on_disk(client, tmp_path, data_dir, damage):
    path = make_zip(tmp_path / "bad.zip", {"S1/IM0001.dcm": dicom_bytes()})
    damaged = corrupt_member(path, "S1/IM0001.dcm") if damage == "corrupt" else mark_encrypted(path)
    res = _upload(client, damaged.read_bytes())
    assert res.status_code == 422 and isinstance(res.json()["detail"], str)
    assert not list((data_dir / "imaging").glob("*/")) and not list((data_dir / "imaging").glob("*.part"))


def test_unexpected_processing_errors_still_delete_the_stored_zip(client, tmp_path, data_dir, monkeypatch):
    def boom(*args, **kwargs):
        raise MemoryError("boom")
    monkeypatch.setattr("routers.imaging.extract_keyframes", boom)
    with pytest.raises(MemoryError):
        _upload(client, _zip_bytes(tmp_path))
    assert not list((data_dir / "imaging").glob("*/"))
