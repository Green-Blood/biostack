"""Nightly backup: one compressed archive holding a consistent copy of the database and the data directory.

    uv run python -m scripts.backup [--keep 14] [--out DIR]

The database is copied with SQLite's own backup API, so the archive is consistent even while the app is writing.
Archives are named biostack-YYYYmmdd-HHMMSS.tar.gz; only the newest --keep of them are kept. The default folder is
`backups/` next to the database file. Restore: stop the app, unpack the archive over the database and data directory.
"""
import argparse
import datetime as dt
import sqlite3
import sys
import tarfile
import tempfile
from collections.abc import Sequence
from pathlib import Path

from config import settings

SQLITE_PREFIX = "sqlite:///"
DEFAULT_KEEP = 14
PATTERN = "biostack-*.tar.gz"
SCRATCH = "data/tmp"  # upload scratch folder inside the archive, left out


class BackupError(Exception):
    """The backup could not be made; nothing was written."""


def run_backup(db_path: Path, data_dir: Path, out_dir: Path, now: dt.datetime, keep: int = DEFAULT_KEEP) -> Path:
    if keep < 1:
        raise BackupError("keep must be at least 1")
    if not db_path.is_file():
        raise BackupError(f"database not found: {db_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"biostack-{now:%Y%m%d-%H%M%S}.tar.gz"
    with tempfile.TemporaryDirectory(dir=out_dir) as scratch:
        copy = Path(scratch) / "biostack.db"
        _copy_database(db_path, copy)
        partial = target.with_suffix(".partial")
        try:
            with tarfile.open(partial, "w:gz") as tar:
                tar.add(copy, arcname="biostack.db")
                if data_dir.is_dir():
                    tar.add(data_dir, arcname="data", filter=_skip_scratch)
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)
    prune(out_dir, keep)
    return target


def _skip_scratch(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """`data/tmp` only holds uploads in flight (e.g. a medical export ZIP); it is never part of a backup."""
    return None if info.name == SCRATCH or info.name.startswith(SCRATCH + "/") else info


def _copy_database(source: Path, destination: Path) -> None:
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(destination)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def prune(out_dir: Path, keep: int) -> None:
    for old in sorted(out_dir.glob(PATTERN))[:-keep]:
        old.unlink()


def _database_file() -> Path:
    url = settings.database_url
    if not url.startswith(SQLITE_PREFIX):
        raise BackupError("only SQLite databases can be backed up with this script")
    return Path(url.removeprefix(SQLITE_PREFIX))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Back up the BioStack database and data directory.")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP, help="how many archives to keep (default 14)")
    parser.add_argument("--out", type=Path, help="folder for archives (default: backups/ next to the database)")
    args = parser.parse_args(argv)
    try:
        db_path = _database_file()
        archive = run_backup(db_path, settings.data_dir, args.out or db_path.parent / "backups", dt.datetime.now(), args.keep)
    except BackupError as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        return 1
    print(f"Backup written: {archive} ({archive.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
