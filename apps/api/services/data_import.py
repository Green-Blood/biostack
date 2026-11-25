"""Import a BioStack export ZIP back into an empty database: every table from data/all-tables.json plus the files.

Only into an empty database (the lost-machine case); merging into existing data is deliberately not supported.
"""
import datetime as dt
import json
import zipfile
from pathlib import Path

from sqlmodel import Session, SQLModel

from config import settings
from services.data_export import MANIFEST, TABLES_JSON, export_all_tables

# tables the app fills by itself on first start; their rows do not count as "existing data"
SELF_FILLED = {"appsetting", "importjob"}


class ImportRefused(Exception):
    """The archive cannot be imported; nothing was changed."""


def _convert(column, value):
    if not isinstance(value, str):
        return value
    try:
        kind = column.type.python_type
    except NotImplementedError:
        return value
    if kind is dt.datetime or type(column.type).__name__ == "UTCDateTime":
        return dt.datetime.fromisoformat(value)
    if kind is dt.date:
        return dt.date.fromisoformat(value)
    if kind is dt.time:
        return dt.time.fromisoformat(value)
    return value


def import_archive(session: Session, zip_path: Path, data_dir: Path | None = None) -> dict:
    data_dir = (data_dir or settings.data_dir).resolve()
    existing = {name: len(rows) for name, rows in export_all_tables(session).items() if rows and name not in SELF_FILLED}
    if existing:
        raise ImportRefused("The database already has data; import only works into an empty database.")
    try:
        z = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise ImportRefused("This is not a BioStack export ZIP.") from exc
    with z:
        if TABLES_JSON not in z.namelist():
            raise ImportRefused("This ZIP has no data/all-tables.json; it is not a BioStack export.")
        tables = json.loads(z.read(TABLES_JSON))
        known = {t.name: t for t in SQLModel.metadata.sorted_tables}
        counts: dict[str, int] = {}
        for table in SQLModel.metadata.sorted_tables:  # parents before children
            rows = tables.get(table.name) or []
            if table.name in SELF_FILLED or not rows:
                continue
            columns = {c.name: c for c in table.columns}
            clean = [{k: _convert(columns[k], v) for k, v in row.items() if k in columns} for row in rows]
            session.execute(table.insert(), clean)
            counts[table.name] = len(clean)
        session.commit()
        files = 0
        manifest = json.loads(z.read(MANIFEST)) if MANIFEST in z.namelist() else {}
        for arc, rel in manifest.items():
            target = (data_dir / rel).resolve()
            if arc not in z.namelist() or not target.is_relative_to(data_dir):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(arc) as src, open(target, "wb") as out:
                while chunk := src.read(1024 * 1024):
                    out.write(chunk)
            files += 1
    return {"tables": counts, "rows": sum(counts.values()), "files": files, "unknown_tables": sorted(set(tables) - set(known))}
