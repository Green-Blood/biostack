"""Attach already-downloaded files to imported Notion records.

Usage: python -m importers.attach_files manifest.json
The manifest is a JSON list of {"page_id": <Notion page id>, "path": <local file>}. Safe to re-run.
"""
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlmodel import Session, select

from db.models import MedicalRecord
from importers.notion_import import SOURCE
from services.attachments import UnsupportedAttachment, attach_file


@dataclass
class AttachReport:
    attached: int = 0
    unknown_pages: int = 0
    missing_files: int = 0
    unsupported: list[str] = field(default_factory=list)


def attach_from_manifest(manifest: Path, session: Session) -> AttachReport:
    report = AttachReport()
    for entry in json.loads(manifest.read_text(encoding="utf-8")):
        record = session.exec(select(MedicalRecord).where(
            MedicalRecord.source == SOURCE, MedicalRecord.external_id == entry["page_id"])).first()
        if record is None:
            report.unknown_pages += 1
            continue
        path = Path(entry["path"])
        if not path.is_file():
            report.missing_files += 1
            continue
        try:
            attach_file(session, record.id, path)
        except UnsupportedAttachment:
            report.unsupported.append(path.name)
            continue
        report.attached += 1
    return report


if __name__ == "__main__":
    from db.database import engine

    with Session(engine) as s:
        print(attach_from_manifest(Path(sys.argv[1]), s))
