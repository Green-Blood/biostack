import datetime as dt
import json

import pytest
from sqlmodel import select

from config import settings
from db.models import Biomarker, LabReport, MedicalRecord
from importers.lab_files import import_lab_files
from tests.pdf_factory import text_pdf


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")


@pytest.fixture
def record(session):
    rec = MedicalRecord(title="Visit", source="notion", external_id="page-1")
    session.add(rec)
    session.commit()
    return rec


def _manifest(tmp_path, entries):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def _lab(tmp_path, name="lab.pdf"):
    path = tmp_path / name
    path.write_bytes(text_pdf("Test Result Reference Unit", "Ferritin 12 30-400 ng/ml"))
    return path


def test_lab_pdfs_become_reports_linked_to_their_record(session, record, tmp_path):
    manifest = _manifest(tmp_path, [{"page_id": "page-1", "path": str(_lab(tmp_path))}])
    report = import_lab_files(manifest, session, fallback_date=dt.date(2025, 1, 2))
    assert (report.imported, report.skipped_not_labs) == (1, 0)
    saved = session.exec(select(LabReport)).one()
    assert saved.record_id == record.id and saved.source == "pdf" and saved.test_date == dt.date(2025, 1, 2)
    biomarker = session.exec(select(Biomarker)).one()
    assert biomarker.marker_key == "ferritin" and biomarker.value == 12 and biomarker.is_out_of_range


def test_running_it_twice_does_not_duplicate(session, record, tmp_path):
    manifest = _manifest(tmp_path, [{"page_id": "page-1", "path": str(_lab(tmp_path))}])
    import_lab_files(manifest, session, fallback_date=dt.date(2025, 1, 2))
    again = import_lab_files(manifest, session, fallback_date=dt.date(2025, 1, 2))
    assert again.already_saved == 1 and len(session.exec(select(LabReport)).all()) == 1


def test_non_lab_files_and_photos_are_left_alone(session, record, tmp_path):
    note = tmp_path / "note.pdf"
    note.write_bytes(text_pdf("Clinic letter with no results"))
    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"\xff\xd8\xff\xe0 photo")
    manifest = _manifest(tmp_path, [{"page_id": "page-1", "path": str(note)}, {"page_id": "page-1", "path": str(photo)}])
    report = import_lab_files(manifest, session, fallback_date=dt.date(2025, 1, 2))
    assert report.imported == 0 and report.skipped_not_labs == 2
    assert session.exec(select(LabReport)).all() == []
