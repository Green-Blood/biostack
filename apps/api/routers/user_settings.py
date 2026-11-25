import datetime as dt
import json

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlmodel import Session

from config import settings as app_config
from db.database import get_session
from services import app_settings
from services.ai_provider import AiNotConfigured, ai_status, check_ai_connection
from services.app_settings import UserSettings
from services.clock import system_zone
from services.data_export import build_archive, export_all_tables
from services.data_import import ImportRefused, import_archive
from services.gemini_client import AiRequestError

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsOut(UserSettings):
    detected_timezone: str


def _with_detected_zone(settings: UserSettings) -> SettingsOut:
    return SettingsOut(**settings.model_dump(), detected_timezone=str(system_zone()))


@router.get("")
def read_settings(session: Session = Depends(get_session)) -> SettingsOut:
    return _with_detected_zone(app_settings.load_settings(session))


@router.put("")
def update_settings(settings: UserSettings, session: Session = Depends(get_session)) -> SettingsOut:
    return _with_detected_zone(app_settings.save_settings(session, settings))


@router.patch("")
def patch_settings(changes: dict, session: Session = Depends(get_session)) -> SettingsOut:
    """Change only the fields sent, so the profile form and the AI switch never overwrite each other."""
    merged = {**app_settings.load_settings(session).model_dump(), **changes}
    try:
        settings = UserSettings.model_validate(merged)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_context=False, include_url=False)) from exc
    return _with_detected_zone(app_settings.save_settings(session, settings))


@router.get("/export")
def export_data(session: Session = Depends(get_session)) -> Response:
    return Response(
        json.dumps(export_all_tables(session), indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="biostack-export.json"'},
    )


@router.get("/export/archive")
def export_archive(include_dicom: bool = False, session: Session = Depends(get_session)) -> FileResponse:
    """Everything in one ZIP: readable CSV/Markdown for people and AIs, the full JSON, and the original files.

    `include_dicom=true` adds the scan DICOM archives (large)."""
    path = build_archive(session, include_dicom=include_dicom)
    return FileResponse(path, media_type="application/zip", filename=f"biostack-export-{dt.date.today()}.zip",
                        background=BackgroundTask(path.unlink, missing_ok=True))


@router.post("/import/archive")
def import_archive_zip(file: UploadFile = File(...), session: Session = Depends(get_session)) -> dict:
    """Restore a BioStack export ZIP into an empty database (tables and files). Refused when data already exists."""
    with tempfile.NamedTemporaryFile(prefix="biostack-import-", suffix=".zip", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
    try:
        return import_archive(session, Path(tmp.name))
    except ImportRefused as exc:
        raise HTTPException(409, str(exc)) from exc
    finally:
        Path(tmp.name).unlink(missing_ok=True)


@router.get("/ai-status")
def read_ai_status() -> dict:
    return ai_status(app_config)


@router.post("/ai-test")
def run_ai_test() -> dict:
    try:
        return check_ai_connection(app_config)
    except (AiNotConfigured, AiRequestError) as exc:
        return {"ok": False, "error": str(exc)}
