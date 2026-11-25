import hashlib
import json

import pytest
from sqlmodel import select

from config import settings
from db.models import MedicalRecord, RecordAttachment
from importers.attach_files import attach_from_manifest
from services import attachments

PDF = b"%PDF-1.4 synthetic visit summary"
JPEG = b"\xff\xd8\xff\xe0 synthetic photo"
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00 synthetic"


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    return tmp_path / "data"


@pytest.fixture
def record(session):
    rec = MedicalRecord(title="Visit", source="notion", external_id="page-1")
    session.add(rec)
    session.commit()
    return rec


def _file(tmp_path, name, content):
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_attach_stores_a_copy_under_its_hash_and_keeps_the_original_name(session, record, tmp_path, data_dir):
    path = _file(tmp_path, "анализы.pdf", PDF)
    att = attachments.attach_file(session, record.id, path)
    digest = hashlib.sha256(PDF).hexdigest()
    assert att.filename == "анализы.pdf" and att.mime_type == "application/pdf" and att.size_bytes == len(PDF)
    assert att.stored_path == f"attachments/{digest}.pdf"
    assert (data_dir / att.stored_path).read_bytes() == PDF
    assert path.exists()  # the source file is left alone


def test_attaching_the_same_file_twice_to_a_record_adds_one_row(session, record, tmp_path):
    first = attachments.attach_file(session, record.id, _file(tmp_path, "a.pdf", PDF))
    second = attachments.attach_file(session, record.id, _file(tmp_path, "copy.pdf", PDF))
    assert first.id == second.id
    assert len(session.exec(select(RecordAttachment)).all()) == 1


def test_same_file_on_two_records_shares_one_stored_copy(session, record, tmp_path, data_dir):
    other = MedicalRecord(title="Other", source="notion", external_id="page-2")
    session.add(other)
    session.commit()
    a = attachments.attach_file(session, record.id, _file(tmp_path, "a.pdf", PDF))
    b = attachments.attach_file(session, other.id, _file(tmp_path, "b.pdf", PDF))
    assert a.id != b.id and a.stored_path == b.stored_path
    assert len(list((data_dir / "attachments").iterdir())) == 1


def test_files_that_are_not_documents_or_photos_are_refused(session, record, tmp_path):
    with pytest.raises(attachments.UnsupportedAttachment):
        attachments.attach_file(session, record.id, _file(tmp_path, "x.txt", b"hello"))


def test_record_lists_its_attachments_and_serves_the_file(client, session, record, tmp_path):
    att = attachments.attach_file(session, record.id, _file(tmp_path, "scan.jpg", JPEG))
    listing = client.get("/api/v1/records").json()[0]
    assert listing["attachment_count"] == 1
    detail = client.get(f"/api/v1/records/{record.id}").json()
    assert detail["attachments"] == [{"id": att.id, "filename": "scan.jpg", "mime_type": "image/jpeg",
                                      "size_bytes": len(JPEG), "is_image": True}]
    res = client.get(f"/api/v1/attachments/{att.id}/file")
    assert res.status_code == 200 and res.content == JPEG
    assert res.headers["content-type"] == "image/jpeg" and res.headers["x-content-type-options"] == "nosniff"


def test_heic_is_listed_and_flagged_as_displayable(client, session, record, tmp_path):
    attachments.attach_file(session, record.id, _file(tmp_path, "p.heic", HEIC))
    item = client.get(f"/api/v1/records/{record.id}").json()["attachments"][0]
    assert item["mime_type"] == "image/heic" and item["is_image"] is True


def test_missing_attachment_is_a_404(client):
    assert client.get("/api/v1/attachments/999/file").status_code == 404


def test_manifest_import_is_idempotent_and_reports_what_it_could_not_place(session, record, tmp_path):
    good = _file(tmp_path, "v.pdf", PDF)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([
        {"page_id": "page-1", "path": str(good)},
        {"page_id": "no-such-page", "path": str(good)},
        {"page_id": "page-1", "path": str(tmp_path / "gone.pdf")},
    ]), encoding="utf-8")
    first = attach_from_manifest(manifest, session)
    again = attach_from_manifest(manifest, session)
    assert (first.attached, first.unknown_pages, first.missing_files) == (1, 1, 1)
    assert len(session.exec(select(RecordAttachment)).all()) == 1
    assert again.attached == 1  # already there counts as attached, never duplicated
