"""Re-check stored lab rows that were unmapped against the current marker catalog.

Usage: python -m importers.remap_markers   (safe to re-run)
"""
from sqlmodel import Session

from services.lab_store import remap_unmapped_biomarkers

if __name__ == "__main__":
    from db.database import engine

    with Session(engine) as s:
        print(f"Mapped {remap_unmapped_biomarkers(s)} previously unmapped rows")
