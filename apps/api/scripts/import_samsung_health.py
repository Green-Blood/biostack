"""Import a Samsung Health export ZIP, synchronously, and print the summary as JSON.
Usage: python -m scripts.import_samsung_health <zip> [--db PATH]   (default: the app's configured database)
Never creates tables (run `alembic upgrade head` first) and never deletes the ZIP you pass."""
import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import inspect
from sqlmodel import Session, create_engine

import db.models  # noqa: F401  (register tables)
from db.models import ImportJob
from services import samsung_import

TABLES = ("importjob", "sleepsession", "sleepstage", "workout", "dailymetric", "bodymeasurement", "appsetting")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip", type=Path, help="the Samsung Health export ZIP")
    parser.add_argument("--db", help="path to a SQLite file; default is the configured database")
    args = parser.parse_args(argv)
    if args.db:
        engine = create_engine(f"sqlite:///{args.db}")
    else:
        from db.database import engine
    present = set(inspect(engine).get_table_names())
    if missing := [t for t in TABLES if t not in present]:
        print(f"Missing tables: {', '.join(missing)}. Run `alembic upgrade head` on this database first.", file=sys.stderr)
        return 2
    if not samsung_import.looks_like_export(args.zip):
        print("Not a Samsung Health export: expected a ZIP with com.samsung.*.csv files.", file=sys.stderr)
        return 3
    with Session(engine) as session:
        if samsung_import.running_job(session) is not None:
            print("An import is already running on this database.", file=sys.stderr)
            return 4
        job_id = samsung_import.create_job(session).id
    samsung_import.run_import(lambda: Session(engine), args.zip, job_id, keep_zip=True)
    with Session(engine) as session:
        job = session.get(ImportJob, job_id)
        if job.status != "done":
            print(f"Import failed ({job.error}). Steps already finished are saved; running again is safe.", file=sys.stderr)
            return 1
        print(json.dumps(job.summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
