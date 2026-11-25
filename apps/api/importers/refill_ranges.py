"""Fill blank reference ranges of stored PDF lab reports from the owner's profile (no AI).

Rows saved blank only because the profile could not decide (sex or age missing) are re-read from the PDF's text layer
and filled once the profile can decide. Ranges the owner cleared or set are never changed. The logic lives in
services.range_refill, shared with POST /api/v1/profile/refill-ranges.

Usage: python -m importers.refill_ranges   (safe to re-run)
"""
from sqlmodel import Session

from services.range_refill import refill_ranges, refill_report  # noqa: F401  (re-exported)

if __name__ == "__main__":
    from db.database import engine

    with Session(engine) as s:
        print(f"Filled ranges for {refill_ranges(s)} results")
