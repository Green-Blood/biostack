from fastapi import APIRouter, Depends
from sqlmodel import Session

from db.database import get_session
from services.demo_data import demo_counts

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/demo")
def demo_status(session: Session = Depends(get_session)) -> dict:
    """Tells the UI whether any rows are demo data, so it can show its banner."""
    counts = {name: count for name, count in demo_counts(session).items() if count}
    return {"demo": bool(counts), "counts": counts}
