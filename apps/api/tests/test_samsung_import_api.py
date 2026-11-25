import json
import zipfile

import pytest
from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine, select

from config import settings
from db.models import DailyMetric, ImportJob, SleepSession, Workout
from routers import imports as imports_router
from services import samsung_import
from services.i18n import EN, RU, msg
from tests.samsung_fixture import build_export


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return tmp_path


@pytest.fixture
def sync(client, engine, monkeypatch):
    """Run the background job inline, with its own sessions on the test engine."""
    from main import app
    app.dependency_overrides[imports_router.get_session_factory] = lambda: (lambda: Session(engine))
    monkeypatch.setattr(imports_router, "launch", lambda target: target())
    return client


@pytest.fixture
def export_zip(tmp_path):
    return build_export(tmp_path / "export.zip")


def _upload(client, content, lang=None, name="export.zip"):
    headers = {"Accept-Language": lang} if lang else {}
    return client.post("/api/v1/imports/samsung-health", files={"file": (name, content, "application/zip")}, headers=headers)


def _tmp_files(data_dir):
    folder = data_dir / "tmp"
    return list(folder.iterdir()) if folder.exists() else []


def test_upload_runs_the_job_stores_data_and_deletes_the_zip(sync, export_zip, engine, data_dir):
    res = _upload(sync, export_zip.read_bytes())
    assert res.status_code == 202
    job = sync.get(f"/api/v1/imports/samsung-health/{res.json()['job_id']}").json()
    assert job["status"] == "done" and job["progress"] == 1.0 and job["stage"] == "done" and job["error"] is None
    s = job["summary"]
    assert set(s) == {"counts", "skipped", "junk", "days", "nights", "workouts", "dropped_workouts", "body", "latest_height_cm"}
    assert s["workouts"]["added"] >= 1 and s["nights"] >= 1 and s["days"] >= 1 and s["body"] >= 1
    assert s["counts"]["sleep"] == 2
    with Session(engine) as session:
        assert session.exec(select(SleepSession)).all() and session.exec(select(Workout)).all()
        assert session.exec(select(DailyMetric)).all()
    assert _tmp_files(data_dir) == []
    assert sync.get("/api/v1/imports/samsung-health/latest").json()["id"] == job["id"]


def test_second_upload_adds_no_workouts(sync, export_zip):
    first = sync.get(f"/api/v1/imports/samsung-health/{_upload(sync, export_zip.read_bytes()).json()['job_id']}").json()
    second = sync.get(f"/api/v1/imports/samsung-health/{_upload(sync, export_zip.read_bytes()).json()['job_id']}").json()
    assert first["summary"]["workouts"]["added"] > 0
    assert second["status"] == "done" and second["summary"]["workouts"]["added"] == 0
    assert second["summary"]["workouts"]["unchanged"] == first["summary"]["workouts"]["added"]


def test_reimport_clears_stale_derived_fields_on_covered_days_only(sync, export_zip, engine):
    import datetime as dt
    covered, outside = dt.date(2026, 10, 2), dt.date(2026, 9, 1)
    with Session(engine) as s:
        s.add(DailyMetric(metric_date=covered, vo2_max=45.0, stress_avg=9.0, source="samsung_export",
                          field_sources={"vo2_max": "samsung_export", "stress_avg": "health_sync"}))
        s.add(DailyMetric(metric_date=outside, vo2_max=44.0, source="samsung_export", field_sources={"vo2_max": "samsung_export"}))
        s.commit()
    job = sync.get(f"/api/v1/imports/samsung-health/{_upload(sync, export_zip.read_bytes()).json()['job_id']}").json()
    assert job["status"] == "done"
    with Session(engine) as s:
        row = s.get(DailyMetric, covered)
        assert row.vo2_max is None and row.stress_avg == 9.0 and row.steps is not None
        assert s.get(DailyMetric, outside).vo2_max == 44.0


def test_summary_counts_nights_not_parts(sync, export_zip, monkeypatch):
    import datetime as dt

    from services.wearable_ingest import SleepIn
    t0 = dt.datetime(2026, 10, 1, 17, 0, tzinfo=dt.UTC)
    wake = dt.date(2026, 10, 2)

    def part(ext, start_h, end_h, main=True):
        return SleepIn(external_id=ext, start_utc=t0 + dt.timedelta(hours=start_h), end_utc=t0 + dt.timedelta(hours=end_h),
                       tz_offset_min=300, wake_date=wake, duration_min=60.0 * (end_h - start_h), is_main=main)
    parts = [part("a", 0, 3), part("b", 4, 8), part("dup", 0, 2, main=False)]
    monkeypatch.setattr(samsung_import, "derive_sleep", lambda *_a: (parts, {}))
    job = sync.get(f"/api/v1/imports/samsung-health/{_upload(sync, export_zip.read_bytes()).json()['job_id']}").json()
    assert job["status"] == "done" and job["summary"]["nights"] == 1


def test_conflict_while_a_job_is_running_is_localized_and_leaves_no_file(sync, export_zip, engine, data_dir):
    with Session(engine) as s:
        s.add(ImportJob(kind=samsung_import.KIND, status="running"))
        s.commit()
    res = _upload(sync, export_zip.read_bytes(), lang="ru")
    assert res.status_code == 409 and res.json()["detail"] == msg("ru", "http.samsung_job_running")
    assert _upload(sync, export_zip.read_bytes()).json()["detail"] == msg("en", "http.samsung_job_running")
    assert _tmp_files(data_dir) == []


def test_non_zip_and_zip_without_samsung_csv_are_415_localized(sync, tmp_path, data_dir):
    res = _upload(sync, b"plain text, not a zip", lang="ru")
    assert res.status_code == 415 and res.json()["detail"] == msg("ru", "http.samsung_not_zip")
    other = tmp_path / "other.zip"
    with zipfile.ZipFile(other, "w") as zf:
        zf.writestr("notes.txt", "hello")
        zf.writestr("data/other.csv", "a,b")
    res = _upload(sync, other.read_bytes())
    assert res.status_code == 415 and res.json()["detail"] == msg("en", "http.samsung_not_zip")
    assert _tmp_files(data_dir) == []


def test_oversized_upload_is_rejected_and_removed(sync, export_zip, data_dir, monkeypatch):
    monkeypatch.setattr(imports_router, "MAX_BYTES", 100)
    assert _upload(sync, export_zip.read_bytes()).status_code == 413
    assert _tmp_files(data_dir) == []


def test_unknown_job_is_404_and_latest_is_null_when_none(sync):
    assert sync.get("/api/v1/imports/samsung-health/latest").json() is None
    assert sync.get("/api/v1/imports/samsung-health/999").status_code == 404


def test_job_running_at_startup_is_marked_failed_with_interrupted_message(sync, engine):
    with Session(engine) as s:
        s.add(ImportJob(kind=samsung_import.KIND, status="running"))
        s.add(ImportJob(kind=samsung_import.KIND, status="done"))
        s.commit()
        assert samsung_import.mark_interrupted(s) == 1
    ru = sync.get("/api/v1/imports/samsung-health/latest", headers={"Accept-Language": "ru"}).json()
    assert ru["status"] == "done"
    job = sync.get("/api/v1/imports/samsung-health/1", headers={"Accept-Language": "ru"}).json()
    assert job["status"] == "failed" and job["error"] == RU["samsung.interrupted"]
    assert sync.get("/api/v1/imports/samsung-health/1").json()["error"] == EN["samsung.interrupted"]
    job = sync.get("/api/v1/imports/samsung-health/1").json()
    assert job["finished_at"].endswith("+00:00") and job["started_at"] is None  # UTC, said so explicitly


def test_job_timestamps_carry_the_utc_offset(sync, engine):
    import datetime as dt
    with Session(engine) as s:
        s.add(ImportJob(kind=samsung_import.KIND, status="done", started_at=dt.datetime(2026, 11, 10, 23, 0, tzinfo=dt.UTC),
                        finished_at=dt.datetime(2026, 11, 10, 23, 30, tzinfo=dt.UTC)))
        s.commit()
    job = sync.get("/api/v1/imports/samsung-health/latest").json()
    assert job["started_at"] == "2026-11-10T23:00:00+00:00" and job["finished_at"] == "2026-11-10T23:30:00+00:00"


def test_failure_mid_run_keeps_earlier_types_fails_the_job_and_deletes_the_zip(sync, export_zip, engine, data_dir, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(samsung_import, "ingest_daily", boom)
    job = sync.get(f"/api/v1/imports/samsung-health/{_upload(sync, export_zip.read_bytes()).json()['job_id']}").json()
    assert job["status"] == "failed" and job["error"] == EN["samsung.failed"] and "disk on fire" not in json.dumps(job)
    with Session(engine) as session:  # sleep and workouts were committed before the failing step
        assert session.exec(select(SleepSession)).all() and session.exec(select(Workout)).all()
        assert session.exec(select(DailyMetric)).all() == []
    assert _tmp_files(data_dir) == []


def test_corrupt_zip_that_passes_the_name_check_fails_cleanly(engine, tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    with Session(engine) as s:
        job_id = samsung_import.create_job(s).id
    samsung_import.run_import(lambda: Session(engine), bad, job_id)
    with Session(engine) as s:
        assert s.get(ImportJob, job_id).status == "failed"
    assert not bad.exists()


def test_background_job_uses_its_own_session(sync, export_zip, engine, monkeypatch):
    opened = []
    monkeypatch.setattr(imports_router, "launch", lambda target: target())
    from main import app
    app.dependency_overrides[imports_router.get_session_factory] = lambda: (lambda: opened.append(1) or Session(engine))
    assert _upload(sync, export_zip.read_bytes()).status_code == 202
    assert opened == [1]


def test_catalogs_have_the_new_keys():
    for key in ("http.samsung_not_zip", "http.samsung_job_running", "http.samsung_job_not_found", "samsung.interrupted", "samsung.failed"):
        assert key in EN and key in RU


def test_factory_failure_still_deletes_the_zip_and_fails_the_job(engine, tmp_path):
    zip_path = tmp_path / "x.zip"
    zip_path.write_bytes(b"x")
    with Session(engine) as s:
        job_id = samsung_import.create_job(s).id
    calls = []

    def factory():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("no connection")
        return Session(engine)
    samsung_import.run_import(factory, zip_path, job_id)
    assert not zip_path.exists() and len(calls) == 2
    with Session(engine) as s:
        assert s.get(ImportJob, job_id).status == "failed"


def test_factory_that_always_fails_does_not_raise_and_deletes_the_zip(tmp_path):
    zip_path = tmp_path / "x.zip"
    zip_path.write_bytes(b"x")

    def factory():
        raise RuntimeError("down")
    samsung_import.run_import(factory, zip_path, 1)
    assert not zip_path.exists()


def test_real_background_thread_imports_into_a_file_backed_database(client, export_zip, tmp_path, data_dir):
    import time

    from main import app
    path = tmp_path / "thread.db"
    engine = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(engine)
    from db.database import get_session

    def request_session():
        with Session(engine) as s:
            yield s
    app.dependency_overrides[get_session] = request_session
    app.dependency_overrides[imports_router.get_session_factory] = lambda: (lambda: Session(engine))
    job_id = _upload(client, export_zip.read_bytes()).json()["job_id"]  # `launch` is the real thread here
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        with Session(engine) as s:
            status = s.get(ImportJob, job_id).status
        if status in ("done", "failed"):
            break
        time.sleep(0.1)
    assert status == "done"
    with Session(engine) as s:
        assert s.exec(select(Workout)).all() and s.exec(select(SleepSession)).all()
    deadline = time.monotonic() + 5
    while _tmp_files(data_dir) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert _tmp_files(data_dir) == []


def test_startup_hook_marks_running_jobs_on_a_scratch_database(tmp_path):
    import main
    engine = create_engine(f"sqlite:///{tmp_path / 'hook.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(ImportJob(kind=samsung_import.KIND, status="running"))
        s.commit()
    main.mark_interrupted_imports_on(engine)
    with Session(engine) as s:
        assert s.get(ImportJob, 1).status == "failed"
    main.mark_interrupted_imports_on(create_engine(f"sqlite:///{tmp_path / 'empty.db'}"))  # unmigrated: no crash


def test_startup_hook_deletes_leftover_upload_zips(tmp_path, data_dir):
    import main
    folder = data_dir / "tmp"
    folder.mkdir()
    (folder / "samsung-abc.zip").write_bytes(b"medical")
    (folder / "samsung-def.zip").write_bytes(b"medical")
    (folder / "other.zip").write_bytes(b"keep")
    main.mark_interrupted_imports_on(create_engine(f"sqlite:///{tmp_path / 'empty.db'}"))  # even with no tables
    assert sorted(p.name for p in folder.iterdir()) == ["other.zip"]
    (folder / "other.zip").unlink()
    folder.rmdir()
    main.mark_interrupted_imports_on(create_engine(f"sqlite:///{tmp_path / 'empty.db'}"))  # no tmp folder: no crash


# ---------------------------------------------------------------- CLI

def test_cli_never_creates_tables(tmp_path, export_zip, capsys):
    import scripts.import_samsung_health as script
    path = tmp_path / "old.db"
    create_engine(f"sqlite:///{path}").dispose()
    assert script.main([str(export_zip), "--db", str(path)]) != 0
    assert "alembic upgrade head" in capsys.readouterr().err
    assert inspect(create_engine(f"sqlite:///{path}")).get_table_names() == []
    assert export_zip.exists()


def test_cli_imports_into_a_scratch_database_and_keeps_the_zip(tmp_path, export_zip, capsys):
    import scripts.import_samsung_health as script
    path = tmp_path / "scratch.db"
    engine = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(engine)
    assert script.main([str(export_zip), "--db", str(path)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["workouts"]["added"] >= 1 and "junk" in summary
    with Session(engine) as s:
        assert s.exec(select(Workout)).all() and s.exec(select(ImportJob)).one().status == "done"
    assert export_zip.exists()


def test_cli_rejects_a_non_samsung_file(tmp_path, capsys):
    import scripts.import_samsung_health as script
    path = tmp_path / "scratch.db"
    SQLModel.metadata.create_all(create_engine(f"sqlite:///{path}"))
    junk = tmp_path / "x.zip"
    junk.write_bytes(b"nope")
    assert script.main([str(junk), "--db", str(path)]) == 3
