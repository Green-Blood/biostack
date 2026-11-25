"""Fill range tiers for stored PDF lab reports by re-reading their text layer (no AI).

Usage: python -m importers.backfill_tiers   (safe to re-run: only markers without tiers are filled)
"""
from sqlmodel import Session, select

from db.models import LabReport
from services.lab_store import fill_report_tiers


def backfill_tiers(session: Session) -> int:
    """Markers filled across every stored PDF report."""
    total = 0
    for report in session.exec(select(LabReport).where(LabReport.source == "pdf")).all():
        total += fill_report_tiers(session, report)
    return total


if __name__ == "__main__":
    from db.database import engine

    with Session(engine) as s:
        print(f"Filled tiers for {backfill_tiers(s)} markers")
