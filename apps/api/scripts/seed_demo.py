"""Optional demo-data seeder. Off by default; it only runs when told exactly which database to touch.

    uv run python -m scripts.seed_demo --yes --db sqlite:////path/to/scratch.db          add demo rows
    uv run python -m scripts.seed_demo --yes --db sqlite:////path/to/scratch.db --remove  delete demo rows

Safety rules: --yes is required; the database must be named with --db or DATABASE_URL (the app's default is
never assumed); the app's own database (the default biostack.db and the file the app's DATABASE_URL setting points
to) is refused unless --force-real is also given, so name a scratch file with --db and do not export it as
DATABASE_URL for this command; the database file must already exist with the schema (run `alembic upgrade head`
on it first); every row written is tagged source="demo", and --remove deletes only those rows.
"""
import argparse
import datetime as dt
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from sqlalchemy import inspect
from sqlmodel import Session, create_engine

from config import ROOT, settings
from services import app_settings
from services.demo_data import remove_demo, seed_demo

DEFAULT_DB = ROOT / "biostack.db"
SQLITE_PREFIX = "sqlite:///"


class Refused(Exception):
    """A safety rule stopped the run; the message says which and what to do."""


def _database_path(target: str | None) -> Path:
    if not target:
        raise Refused("Name the database with --db (or DATABASE_URL); the default database is never assumed.")
    path = Path(target.removeprefix(SQLITE_PREFIX)).expanduser()
    if str(path) == ":memory:":
        raise Refused("Only a SQLite file can be seeded. Give a file path or a sqlite:///... URL.")
    return path.resolve()


def _check(args: argparse.Namespace, env: Mapping[str, str]) -> Path:
    if not args.yes:
        raise Refused("Pass --yes to confirm that this database may be changed.")
    path = _database_path(args.db or env.get("DATABASE_URL"))
    if not args.force_real and path in {DEFAULT_DB.resolve(), _database_path(settings.database_url)}:
        raise Refused("This is the app's real database. Use a scratch database, or add --force-real if you really mean it.")
    if not path.is_file():
        raise Refused(f"{path} does not exist. Create it first with `alembic upgrade head` and DATABASE_URL set to it.")
    return path


def _require_schema(engine) -> None:
    if not inspect(engine).has_table("dailymetric"):
        raise Refused("The database has no tables yet. Run `alembic upgrade head` with DATABASE_URL set to it first.")


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] = os.environ) -> int:
    parser = argparse.ArgumentParser(description="Add or remove demo data in a scratch database.")
    parser.add_argument("--yes", action="store_true", help="confirm the change")
    parser.add_argument("--db", help="SQLite file path or sqlite:///... URL (else DATABASE_URL)")
    parser.add_argument("--force-real", action="store_true", help="allow the default biostack.db")
    parser.add_argument("--remove", action="store_true", help="delete the demo rows instead of adding them")
    args = parser.parse_args(argv)
    try:
        path = _check(args, env)
        engine = create_engine(f"{SQLITE_PREFIX}{path}")
        _require_schema(engine)
    except Refused as refusal:
        print(f"Refused: {refusal}", file=sys.stderr)
        return 2
    with Session(engine) as session:
        if args.remove:
            counts = remove_demo(session)
            print(f"Removed demo rows: {sum(counts.values())}")
        else:
            counts = seed_demo(session, dt.datetime.now(dt.timezone.utc).astimezone(app_settings.configured_zone(session)).date())
            print(f"Seeded demo rows: {sum(counts.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
