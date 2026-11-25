"""Tag existing imaging records and read their measurements (rule-based).
Usage: python -m scripts.backfill_scans [--db PATH]   (default: the app's configured database)
Never creates tables: the scan tables come from `alembic upgrade head`."""
import argparse
import json
import sys
from collections.abc import Sequence

from sqlalchemy import inspect
from sqlmodel import Session, create_engine

import db.models  # noqa: F401  (register tables)
from services.scan_store import backfill

SCAN_TABLES = ("medicalrecord", "recordorgan", "scanmeasurement")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", help="path to a SQLite file; default is the configured database")
    args = parser.parse_args(argv)
    if args.db:
        engine = create_engine(f"sqlite:///{args.db}")
    else:
        from db.database import engine
    present = set(inspect(engine).get_table_names())
    if missing := [t for t in SCAN_TABLES if t not in present]:
        print(f"Missing tables: {', '.join(missing)}. Run `alembic upgrade head` on this database first.", file=sys.stderr)
        return 2
    with Session(engine) as session:
        print(json.dumps(backfill(session)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
