import threading
import uuid
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from config import settings
from db import database
from db.database import get_session
from db.models import ImportJob
from services import apple_health_import, samsung_import
from services.i18n import EN, Lang, get_lang, msg

router = APIRouter(prefix="/imports/samsung-health", tags=["imports"])
apple_router = APIRouter(prefix="/imports/apple-health", tags=["imports"])

MAX_BYTES = 300 * 1024**2
CHUNK_BYTES = 1024**2


def get_session_factory() -> Callable[[], Session]:
    """The background thread opens its own sessions from this; tests override it."""
    return lambda: Session(database.engine)


def launch(target: Callable[[], None]) -> None:
    threading.Thread(target=target, name="samsung-import", daemon=True).start()


class JobOut(BaseModel):
    id: int
    status: str
    progress: float
    stage: str
    summary: dict
    error: str | None
    started_at: str | None
    finished_at: str | None

    @classmethod
    def of(cls, job: ImportJob, lang: str) -> "JobOut":
        error = msg(lang, job.error) if job.error in EN else job.error
        return cls(id=job.id, status=job.status, progress=job.progress, stage=job.stage, summary=job.summary or {},
                   error=error, started_at=job.started_at.isoformat() if job.started_at else None,
                   finished_at=job.finished_at.isoformat() if job.finished_at else None)


async def _spool(file: UploadFile, target: Path, lang: Lang) -> None:
    size = 0
    try:
        with target.open("wb") as out:
            while chunk := await file.read(CHUNK_BYTES):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, msg(lang, "http.zip_too_large", mb=MAX_BYTES // 1024**2))
                out.write(chunk)
    except BaseException:
        target.unlink(missing_ok=True)
        raise


@router.post("", status_code=202)
async def start_import(file: UploadFile = File(...), session: Session = Depends(get_session),
                       factory: Callable[[], Session] = Depends(get_session_factory),
                       lang: Lang = Depends(get_lang)) -> dict:
    if samsung_import.running_job(session) is not None:
        raise HTTPException(409, msg(lang, "http.samsung_job_running"))
    tmp = settings.data_dir / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    target = tmp / f"samsung-{uuid.uuid4().hex}.zip"
    await _spool(file, target, lang)
    try:
        if not samsung_import.looks_like_export(target):
            raise HTTPException(415, msg(lang, "http.samsung_not_zip"))
        job = samsung_import.create_job(session)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    job_id = job.id
    launch(lambda: samsung_import.run_import(factory, target, job_id))
    return {"job_id": job_id}


@router.get("/latest")
def latest_job(session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> JobOut | None:
    job = session.exec(select(ImportJob).where(ImportJob.kind == samsung_import.KIND).order_by(ImportJob.id.desc())).first()
    return JobOut.of(job, lang) if job else None


@router.get("/{job_id}")
def get_job(job_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> JobOut:
    job = session.get(ImportJob, job_id)
    if job is None or job.kind != samsung_import.KIND:
        raise HTTPException(404, msg(lang, "http.samsung_job_not_found"))
    return JobOut.of(job, lang)


@apple_router.post("")
async def import_apple_health(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    lang: Lang = Depends(get_lang),
) -> dict:
    tmp = settings.data_dir / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    target = tmp / f"apple-{uuid.uuid4().hex}.zip"
    try:
        await _spool(file, target, lang)
        if not apple_health_import.looks_like_apple_health_zip(target):
            raise HTTPException(415, msg(lang, "http.apple_not_zip"))
        return apple_health_import.import_apple_health_zip(session, target)
    finally:
        target.unlink(missing_ok=True)
