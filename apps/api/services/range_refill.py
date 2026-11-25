"""Fill reference ranges of stored PDF lab reports from the owner's profile (no AI).

A row is filled only when it was saved blank BECAUSE the profile could not decide (its stored `needs_profile` is set),
still has no range, and its printed line is identified unambiguously by (name, value, unit). A range the owner
cleared on purpose, or one that was never profile-dependent, is never restored.
"""
import collections

from sqlmodel import Session, select

from db.models import Biomarker, LabReport
from services.lab_rows import is_out_of_range
from services.lab_store import pdf_file
from services.lab_text_parser import extract_pdf_text, parse_lab_text


def refill_report(session: Session, report: LabReport) -> int:
    stored = pdf_file(report.file_hash) if report.file_hash else None
    if stored is None or stored.suffix != ".pdf":
        return 0
    parsed = parse_lab_text(extract_pdf_text(stored.read_bytes()), session, on_date=report.test_date)
    if parsed is None:
        return 0
    seen = collections.Counter((r.name, r.value, r.unit) for r in parsed.rows)
    unique = {(r.name, r.value, r.unit): r for r in parsed.rows if seen[(r.name, r.value, r.unit)] == 1}
    filled = 0
    for b in session.exec(select(Biomarker).where(Biomarker.report_id == report.id)):
        if b.needs_profile is None or b.ref_min is not None or b.ref_max is not None:
            continue
        row = unique.get((b.raw_name, b.value, b.unit))
        if row is None:
            continue
        if row.ref_min is None and row.ref_max is None:
            if row.needs_profile is not None and row.needs_profile != b.needs_profile:
                b.needs_profile = row.needs_profile  # part of the profile arrived; say what is still missing
                session.add(b)
            continue
        b.ref_min, b.ref_max, b.needs_profile = row.ref_min, row.ref_max, None
        b.is_out_of_range = is_out_of_range(b.value, b.ref_min, b.ref_max)
        session.add(b)
        filled += 1
    session.commit()
    return filled


def refill_ranges(session: Session) -> int:
    """Biomarker rows filled across every stored PDF report."""
    return sum(refill_report(session, r) for r in session.exec(select(LabReport).where(LabReport.source == "pdf")).all())
