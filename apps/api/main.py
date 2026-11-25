import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI

from config import settings
from routers import (
    analytics, chat, cns, courses, environment, freshness, health, health_sync, imaging, imports, inbox, insights, journal, lab_uploads, labs, meta, organs, profile, record_items, records, review, scans, search, signals,
    supplements, user_settings,
)
from security import require_token
from services.log_redaction import RedactSearchQuery
from services.scheduler import start_scheduler

logging.getLogger("uvicorn.access").addFilter(RedactSearchQuery())


def _mark_interrupted_imports() -> None:
    from db.database import engine
    mark_interrupted_imports_on(engine)


def mark_interrupted_imports_on(engine) -> None:
    """A `running` import at start-up died with the previous process; say so instead of showing it as running forever,
    and delete the export ZIP it left behind."""
    from sqlmodel import Session

    from services.samsung_import import mark_interrupted, remove_leftover_uploads
    try:
        remove_leftover_uploads(settings.data_dir)
    except OSError:
        logging.getLogger(__name__).warning("could not remove leftover import uploads")
    try:
        with Session(engine) as session:
            mark_interrupted(session)
    except Exception:  # noqa: BLE001 - a database that is not migrated yet must not stop the API from starting
        logging.getLogger(__name__).warning("could not check for interrupted imports")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    _mark_interrupted_imports()
    scheduler = start_scheduler() if settings.enable_scheduler else None
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="BioStack API", lifespan=lifespan)
app.include_router(health.router)
app.include_router(health_sync.webhook)

api = APIRouter(prefix="/api/v1", dependencies=[Depends(require_token)])
api.include_router(records.router)
api.include_router(record_items.router)
api.include_router(labs.router)
api.include_router(lab_uploads.router)
api.include_router(imaging.router)
api.include_router(review.router)
api.include_router(scans.router)
api.include_router(organs.router)
api.include_router(supplements.router)
api.include_router(journal.router)
api.include_router(cns.router)
api.include_router(health_sync.metrics)
api.include_router(environment.router)
api.include_router(user_settings.router)
api.include_router(analytics.router)
api.include_router(meta.router)
api.include_router(search.router)
api.include_router(inbox.router)
api.include_router(imports.router)
api.include_router(imports.apple_router)
api.include_router(signals.router)
api.include_router(freshness.router)
api.include_router(courses.router)
api.include_router(profile.router)
api.include_router(chat.router)
api.include_router(insights.router)
app.include_router(api)
