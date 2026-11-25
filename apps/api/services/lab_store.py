"""Persisting reviewed lab results and the PDFs they came from."""
import datetime as dt
import json
from pathlib import Path

from sqlmodel import Session, select

from config import settings
from db.models import Biomarker, LabReport, MarkerTier
from services.documents import KNOWN_DOCUMENTS
from services.lab_rows import ReviewedRow, resolve_row
from services.markers import canonical_unit, normalize_marker
from services.tiers import replace_report_tiers

EDITABLE_SOURCES = {"pdf", "manual"}


DOCUMENT_EXTENSIONS = tuple(kind.extension for kind in KNOWN_DOCUMENTS)


def pdf_relpath(file_hash: str, extension: str = ".pdf") -> str:
    return f"pdf/{file_hash}{extension}"


def pdf_file(file_hash: str) -> Path | None:
    """The stored original of an upload (whatever its type), or None when it is not on disk."""
    for extension in DOCUMENT_EXTENSIONS:
        path = settings.data_dir / pdf_relpath(file_hash, extension)
        if path.exists():
            return path
    return None


def draft_file(file_hash: str) -> Path:
    return settings.data_dir / "pdf" / f"{file_hash}.draft.json"


def store_original(file_hash: str, content: bytes, extension: str) -> None:
    (settings.data_dir / "pdf").mkdir(parents=True, exist_ok=True)
    (settings.data_dir / pdf_relpath(file_hash, extension)).write_bytes(content)


def save_pdf_and_draft(file_hash: str, content: bytes, extension: str, draft_json: str) -> None:
    store_original(file_hash, content, extension)
    draft_file(file_hash).write_text(draft_json, encoding="utf-8")


def find_report_by_hash(session: Session, file_hash: str) -> LabReport | None:
    return session.exec(select(LabReport).where(LabReport.file_hash == file_hash)).first()


def save_report(session: Session, *, test_date: dt.date, lab_name: str, rows: list[ReviewedRow],
                source: str, file_hash: str | None = None, record_id: int | None = None) -> LabReport:
    stored = pdf_file(file_hash) if file_hash else None
    report = LabReport(test_date=test_date, lab_name=lab_name.strip(), source=source, file_hash=file_hash,
                       record_id=record_id,
                       external_id=file_hash,
                       pdf_path=pdf_relpath(file_hash, stored.suffix if stored else ".pdf") if file_hash else None)
    session.add(report)
    session.flush()
    for index, row in enumerate(rows):
        draft = resolve_row(row, session)
        blank = draft.ref_min is None and draft.ref_max is None
        session.add(Biomarker(
            report_id=report.id, marker_key=draft.marker_key, display_name=draft.display_name,
            raw_name=draft.name, value=draft.value, result_text=draft.result_text, unit=draft.unit,
            ref_min=draft.ref_min, ref_max=draft.ref_max, is_out_of_range=draft.is_out_of_range,
            needs_profile=draft.needs_profile if blank else None, source=source, external_id=f"{file_hash}#{index}" if file_hash else None))
        if draft.mapped and draft.tiers:
            replace_report_tiers(session, report.id, draft.marker_key, draft.unit, draft.tiers)
    session.commit()
    if file_hash and any("needs_profile" not in r.model_fields_set for r in rows):
        fill_report_needs_profile(session, report, {i for i, r in enumerate(rows) if "needs_profile" not in r.model_fields_set})
    if file_hash and not session.exec(select(MarkerTier).where(MarkerTier.report_id == report.id)).first():
        fill_report_tiers(session, report)  # the reviewed rows carried none: read what the stored PDF printed
    session.refresh(report)
    return report


def fill_report_needs_profile(session: Session, report: LabReport, indexes: set[int]) -> int:
    """For rows saved by a client that did not say, read from the stored PDF whether a blank range is blank only
    because the profile could not decide it. Rows are matched by (name, value, unit); a repeated key is skipped."""
    import collections

    from services.lab_text_parser import extract_pdf_text, parse_lab_text

    stored = pdf_file(report.file_hash) if report.file_hash else None
    if stored is None or stored.suffix != ".pdf":
        return 0
    parsed = parse_lab_text(extract_pdf_text(stored.read_bytes()), None)  # profile-blind: what the profile would be asked for
    if parsed is None:
        return 0
    seen = collections.Counter((r.name, r.value, r.unit) for r in parsed.rows)
    needs = {(r.name, r.value, r.unit): r.needs_profile for r in parsed.rows
             if r.needs_profile and seen[(r.name, r.value, r.unit)] == 1}
    filled = 0
    for b in session.exec(select(Biomarker).where(Biomarker.report_id == report.id)):
        index = int(b.external_id.rsplit("#", 1)[1]) if b.external_id and "#" in b.external_id else None
        if index in indexes and b.ref_min is None and b.ref_max is None and (b.raw_name, b.value, b.unit) in needs:
            b.needs_profile = needs[(b.raw_name, b.value, b.unit)]
            session.add(b)
            filled += 1
    session.commit()
    return filled


def fill_report_tiers(session: Session, report: LabReport) -> int:
    """Add the tiers a stored PDF printed for markers of this report that have none yet; returns markers filled."""
    from services.lab_text_parser import extract_pdf_text, parse_lab_text

    stored = pdf_file(report.file_hash) if report.file_hash else None
    if stored is None or stored.suffix != ".pdf":
        return 0
    parsed = parse_lab_text(extract_pdf_text(stored.read_bytes()), session)
    if parsed is None:
        return 0
    have = {t.marker_key for t in session.exec(select(MarkerTier).where(MarkerTier.report_id == report.id))}
    mine = {b.marker_key for b in session.exec(select(Biomarker).where(Biomarker.report_id == report.id))}
    filled = 0
    for row in parsed.rows:
        if row.mapped and row.tiers and row.marker_key in mine and row.marker_key not in have:
            replace_report_tiers(session, report.id, row.marker_key, row.unit, row.tiers)
            have.add(row.marker_key)
            filled += 1
    session.commit()
    return filled


def delete_report(session: Session, report: LabReport) -> None:
    for biomarker in session.exec(select(Biomarker).where(Biomarker.report_id == report.id)):
        session.delete(biomarker)
    for tier in session.exec(select(MarkerTier).where(MarkerTier.report_id == report.id)):
        session.delete(tier)
    session.delete(report)
    session.commit()
    if report.file_hash:
        stored = pdf_file(report.file_hash)
        if stored is not None:
            stored.unlink(missing_ok=True)
        draft_file(report.file_hash).unlink(missing_ok=True)


def read_cached_draft(file_hash: str) -> dict | None:
    path = draft_file(file_hash)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def remap_unmapped_biomarkers(session: Session) -> int:
    """Map stored rows that were unknown when saved but whose printed name the catalog now recognises."""
    changed = 0
    for biomarker in session.exec(select(Biomarker).where(Biomarker.marker_key.startswith("unmapped:"))):
        match = normalize_marker(biomarker.raw_name or biomarker.display_name, session)
        if match is not None:
            biomarker.marker_key, biomarker.display_name = match.marker_key, match.display_name
            biomarker.unit = canonical_unit(match.marker_key, biomarker.unit or "")
            session.add(biomarker)
            changed += 1
    session.commit()
    return changed
