import datetime as dt
import sqlite3
import tarfile
from pathlib import Path

import pytest

from scripts.backup import BackupError, prune, run_backup

NOW = dt.datetime(2026, 11, 12, 3, 0, 5)


@pytest.fixture
def state(tmp_path: Path) -> dict[str, Path]:
    db = tmp_path / "biostack.db"
    conn = sqlite3.connect(db)
    try:
        with conn:
            conn.execute("create table note (id integer primary key, body text)")
            conn.execute("insert into note (body) values ('first')")
    finally:
        conn.close()
    data = tmp_path / "data"
    (data / "pdf").mkdir(parents=True)
    (data / "pdf" / "a.pdf").write_bytes(b"%PDF-1.4 original")
    return {"db": db, "data": data, "out": tmp_path / "backups"}


def make(state: dict[str, Path], now: dt.datetime = NOW, keep: int = 14) -> Path:
    return run_backup(state["db"], state["data"], state["out"], now, keep)


def test_archive_holds_a_consistent_database_copy_and_the_data_files(state, tmp_path):
    archive = make(state)
    assert archive.name == "biostack-20261112-030005.tar.gz"
    extracted = tmp_path / "restore"
    with tarfile.open(archive) as tar:
        tar.extractall(extracted, filter="data")
    with sqlite3.connect(extracted / "biostack.db") as conn:
        assert conn.execute("select body from note").fetchall() == [("first",)]
    assert (extracted / "data" / "pdf" / "a.pdf").read_bytes() == b"%PDF-1.4 original"


def test_upload_scratch_folder_is_not_backed_up(state, tmp_path):
    (state["data"] / "tmp").mkdir()
    (state["data"] / "tmp" / "samsung-abc.zip").write_bytes(b"medical export")
    (state["data"] / "tmpfiles").mkdir()
    (state["data"] / "tmpfiles" / "keep.txt").write_bytes(b"keep")
    with tarfile.open(make(state)) as tar:
        names = tar.getnames()
    assert not any(n == "data/tmp" or n.startswith("data/tmp/") for n in names)
    assert "data/pdf/a.pdf" in names and "data/tmpfiles/keep.txt" in names


def test_database_written_after_the_backup_is_not_in_it(state, tmp_path):
    archive = make(state)
    with sqlite3.connect(state["db"]) as conn:
        conn.execute("insert into note (body) values ('later')")
    with tarfile.open(archive) as tar:
        tar.extractall(tmp_path / "restore", filter="data")
    with sqlite3.connect(tmp_path / "restore" / "biostack.db") as conn:
        assert conn.execute("select count(*) from note").fetchone() == (1,)


def test_the_source_database_is_never_modified(state):
    before = state["db"].read_bytes()
    make(state)
    assert state["db"].read_bytes() == before


def test_missing_data_directory_still_backs_up_the_database(state, tmp_path):
    state["data"].rename(tmp_path / "gone")
    archive = make(state)
    with tarfile.open(archive) as tar:
        assert tar.getnames() == ["biostack.db"]


def test_missing_database_is_refused_and_leaves_no_archive(state):
    state["db"].unlink()
    with pytest.raises(BackupError, match="database"):
        make(state)
    assert not state["out"].exists()


def test_keeps_only_the_newest_archives(state):
    for day in range(1, 6):
        make(state, dt.datetime(2026, 11, day, 3, 0, 0), keep=3)
    names = sorted(p.name for p in state["out"].glob("biostack-*.tar.gz"))
    assert names == ["biostack-20261103-030000.tar.gz", "biostack-20261104-030000.tar.gz", "biostack-20261105-030000.tar.gz"]


def test_prune_ignores_files_that_are_not_backups(tmp_path):
    (tmp_path / "notes.txt").write_text("keep me")
    for day in (1, 2):
        (tmp_path / f"biostack-2026110{day}-030000.tar.gz").write_bytes(b"x")
    prune(tmp_path, keep=1)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["biostack-20261102-030000.tar.gz", "notes.txt"]


def test_keep_must_be_at_least_one(state):
    with pytest.raises(BackupError, match="keep"):
        make(state, keep=0)
