"""Turn already-downloaded lab PDFs into stored lab results, read from their own text (no AI).

Usage: python -m importers.lab_files manifest.json
The manifest is the one used by importers.attach_files: [{"page_id": <Notion page id>, "path": <local file>}].
Only PDFs whose text holds a results table are imported; everything else (scans, photos, clinical notes) is left
for the upload screen. Safe to re-run: a file already saved is never saved twice.
"""
import datetime as dt
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session, select

from db.models import MedicalRecord
from importers.notion_import import SOURCE
from services import lab_store
from services.documents import PDF_KIND, sniff_document
from services.lab_rows import ReviewedRow
from services.lab_text_parser import extract_pdf_text, parse_lab_text


@dataclass
class LabImportReport:
    imported: int = 0
    already_saved: int = 0
    skipped_not_labs: int = 0
    skipped_no_date: int = 0


def _valid_rows(draft_rows) -> list[ReviewedRow]:
    rows = []
    for row in draft_rows:
        try:
            rows.append(ReviewedRow(**row.model_dump(include={"name", "value", "unit", "ref_min", "ref_max", "result_text", "needs_profile"})))
        except ValueError:
            continue  # a row the parser misread (e.g. a reversed range) is dropped, not allowed to sink the file
    return rows


def import_lab_files(manifest: Path, session: Session, fallback_date: dt.date | None = None) -> LabImportReport:
    report = LabImportReport()
    for entry in json.loads(manifest.read_text(encoding="utf-8")):
        path = Path(entry["path"])
        content = path.read_bytes() if path.is_file() else b""
        parsed = parse_lab_text(extract_pdf_text(content), session) if sniff_document(content) == PDF_KIND else None
        if parsed is None:
            report.skipped_not_labs += 1
            continue
        file_hash = hashlib.sha256(content).hexdigest()
        if lab_store.find_report_by_hash(session, file_hash) is not None:
            report.already_saved += 1
            continue
        test_date = parsed.test_date or fallback_date
        if test_date is None:
            report.skipped_no_date += 1
            continue
        record = session.exec(select(MedicalRecord).where(
            MedicalRecord.source == SOURCE, MedicalRecord.external_id == entry["page_id"])).first()
        lab_store.store_original(file_hash, content, PDF_KIND.extension)
        rows = _valid_rows(parsed.rows)
        lab_store.save_report(session, test_date=test_date, lab_name=parsed.lab_name, rows=rows, source="pdf",
                              file_hash=file_hash, record_id=record.id if record else None)
        report.imported += 1
    return report


if __name__ == "__main__":
    from db.database import engine

    with Session(engine) as s:
        print(import_lab_files(Path(sys.argv[1]), s))
