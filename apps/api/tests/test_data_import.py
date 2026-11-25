import datetime as dt
import zipfile

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from db.models import BodyMeasurement, ImagingStudy, LabReport, MedicalRecord, Profile
from services.data_export import build_archive, export_all_tables
from services.data_import import ImportRefused, import_archive


def _fresh_session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return Session(eng)


def _filled(session, data_dir):
    (data_dir / "imaging" / "abc").mkdir(parents=True)
    (data_dir / "imaging" / "abc" / "f0.png").write_bytes(b"png")
    (data_dir / "imaging" / "abc" / "scan.zip").write_bytes(b"dicom")
    session.add(Profile(birth_date=dt.date(1990, 1, 2), sex="male", height_cm=180))
    session.add(BodyMeasurement(measured_on=dt.date(2024, 5, 25), kind="phase_angle", value=7.33))
    session.add(MedicalRecord(record_type="visit", title="Checkup", record_date=dt.date(2024, 5, 25)))
    session.add(ImagingStudy(study_date=dt.date(2024, 5, 1), study_type="MRI", zip_path="imaging/abc/scan.zip",
                             keyframe_paths=["imaging/abc/f0.png"], file_hash="abc"))
    session.commit()


def test_round_trip_restores_rows_and_files(session, tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir(), dst.mkdir()
    _filled(session, src)
    archive = build_archive(session, src, include_dicom=True)
    target = _fresh_session()
    result = import_archive(target, archive, dst)
    assert result["rows"] >= 4 and result["files"] == 2
    assert export_all_tables(target) == export_all_tables(session)
    assert (dst / "imaging" / "abc" / "scan.zip").read_bytes() == b"dicom"


def test_dicom_is_left_out_unless_asked(session, tmp_path):
    _filled(session, tmp_path)
    names = zipfile.ZipFile(build_archive(session, tmp_path)).namelist()
    assert "imaging/abc/f0.png" in names and "imaging/abc/scan.zip" not in names


def test_refuses_a_database_that_already_has_data(session, tmp_path):
    _filled(session, tmp_path)
    archive = build_archive(session, tmp_path)
    with pytest.raises(ImportRefused):
        import_archive(session, archive, tmp_path)


def test_rejects_a_zip_that_is_not_an_export(tmp_path):
    bad = tmp_path / "x.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("hello.txt", "hi")
    with pytest.raises(ImportRefused):
        import_archive(_fresh_session(), bad, tmp_path)


def test_a_manifest_path_cannot_leave_the_data_folder(session, tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir(), dst.mkdir()
    _filled(session, src)
    archive = build_archive(session, src)
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive) as zin, zipfile.ZipFile(evil, "w") as zout:
        for name in zin.namelist():
            zout.writestr(name, zin.read(name) if name != "data/files-manifest.json" else '{"imaging/abc/f0.png": "../escaped.png"}')
    import_archive(_fresh_session(), evil, dst)
    assert not (tmp_path / "escaped.png").exists()
