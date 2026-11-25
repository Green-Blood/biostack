import datetime as dt
import hashlib
from collections.abc import Callable
from functools import partial
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from config import settings
from db.database import get_session
from db.models import ImagingStudy
from services import imaging_store
from services.ai_provider import AiNotConfigured, build_report_reader
from services.dicom_processor import DicomArchiveError, extract_keyframes
from services.gemini_client import AiRequestError
from services.gemini_parser import ParseError
from services.i18n import Lang, get_lang, msg, translate_text
from services.report_reader import ReportReader, ReportText

router = APIRouter(prefix="/imaging", tags=["imaging"])

MAX_ZIP_BYTES = 1024 * 1024**2
MAX_REPORT_BYTES = 20 * 1024**2
CHUNK_BYTES = 1024**2
REPORT_TYPES = {b"%PDF-": "application/pdf", b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg"}


class StudyOut(BaseModel):
    id: int
    study_date: dt.date
    study_type: str
    body_part: str
    summary_text: str
    findings_text: str
    series_description: str
    slice_count: int
    frame_count: int

    @classmethod
    def of(cls, study: ImagingStudy) -> "StudyOut":
        return cls(id=study.id, study_date=study.study_date, study_type=study.study_type, body_part=study.body_part,
                   summary_text=study.summary_text, findings_text=study.findings.get("text", ""),
                   series_description=study.series_description, slice_count=study.slice_count,
                   frame_count=len(study.keyframe_paths))


class UploadedStudy(StudyOut):
    warnings: list[str]


class StudyPatch(BaseModel):
    study_date: dt.date | None = None
    study_type: str | None = None
    body_part: str | None = None
    summary_text: str | None = None
    findings_text: str | None = None


def get_report_reader_factory() -> Callable[[], ReportReader]:
    return partial(build_report_reader, settings)


def _get_study(session: Session, study_id: int, lang: Lang) -> ImagingStudy:
    study = session.get(ImagingStudy, study_id)
    if study is None:
        raise HTTPException(404, msg(lang, "http.imaging_not_found"))
    return study


async def _spool_upload(file: UploadFile, target: Path, lang: Lang) -> str:
    """Stream the upload to `target` and return its SHA-256; large scans never sit in memory."""
    digest, size = hashlib.sha256(), 0
    try:
        with target.open("wb") as out:
            while chunk := await file.read(CHUNK_BYTES):
                size += len(chunk)
                if size > MAX_ZIP_BYTES:
                    raise HTTPException(413, msg(lang, "http.zip_too_large", mb=MAX_ZIP_BYTES // 1024**2))
                digest.update(chunk)
                out.write(chunk)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return digest.hexdigest()


@router.post("/upload", status_code=201)
async def upload_study(file: UploadFile = File(...), study_type: str = Form(""), body_part: str = Form(""),
                       study_date: dt.date | None = Form(None),
                       session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> UploadedStudy:
    upload = imaging_store.new_upload_path()
    file_hash = await _spool_upload(file, upload, lang)
    existing = imaging_store.find_by_hash(session, file_hash)
    if existing is not None:
        upload.unlink(missing_ok=True)
        raise HTTPException(409, {"message": msg(lang, "http.archive_already_saved"), "study_id": existing.id})
    zip_path = imaging_store.adopt_upload(upload, file_hash)
    try:
        result = extract_keyframes(zip_path, imaging_store.study_folder(file_hash))
        date = study_date or result.metadata.study_date
        if date is None:
            raise DicomArchiveError("This archive does not contain a study date. Enter the study date and upload again.")
    except Exception as exc:
        imaging_store.discard_folder(file_hash)
        if isinstance(exc, DicomArchiveError):
            raise HTTPException(422, translate_text(lang, str(exc))) from exc
        raise
    meta = result.metadata
    study = ImagingStudy(
        study_date=date, study_type=study_type.strip() or meta.study_type or "Imaging",
        body_part=body_part.strip() or meta.body_part or meta.study_description,
        zip_path=imaging_store.zip_relpath(file_hash), keyframe_paths=[imaging_store.relative_to_data(p) for p in result.frames],
        file_hash=file_hash, series_description=meta.series_description, slice_count=meta.slice_count)
    session.add(study)
    session.commit()
    session.refresh(study)
    return UploadedStudy(**StudyOut.of(study).model_dump(), warnings=[translate_text(lang, w) for w in result.warnings])


@router.get("")
def list_studies(session: Session = Depends(get_session)) -> list[StudyOut]:
    studies = session.exec(select(ImagingStudy).order_by(ImagingStudy.study_date.desc(), ImagingStudy.id.desc()))
    return [StudyOut.of(s) for s in studies]


@router.get("/{study_id}")
def get_study(study_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> StudyOut:
    return StudyOut.of(_get_study(session, study_id, lang))


@router.get("/{study_id}/frames/{index}")
def get_frame(study_id: int, index: int, session: Session = Depends(get_session),
              lang: Lang = Depends(get_lang)) -> FileResponse:
    path = imaging_store.frame_file(_get_study(session, study_id, lang), index)
    if path is None:
        raise HTTPException(404, msg(lang, "http.keyframe_not_found"))
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.patch("/{study_id}")
def edit_study(study_id: int, body: StudyPatch, session: Session = Depends(get_session),
               lang: Lang = Depends(get_lang)) -> StudyOut:
    study = _get_study(session, study_id, lang)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if "findings_text" in changes:
        study.findings = {"text": changes.pop("findings_text")}
    for field, value in changes.items():
        setattr(study, field, value)
    session.add(study)
    session.commit()
    session.refresh(study)
    return StudyOut.of(study)


@router.delete("/{study_id}", status_code=204)
def delete_study(study_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> Response:
    imaging_store.delete_study(session, _get_study(session, study_id, lang))
    return Response(status_code=204)


@router.post("/{study_id}/report")
async def read_report(study_id: int, file: UploadFile = File(...), session: Session = Depends(get_session),
                      reader_factory: Callable[[], ReportReader] = Depends(get_report_reader_factory),
                      lang: Lang = Depends(get_lang)) -> ReportText:
    """Draft summary and findings from a report file. Nothing is stored until the owner saves the edited text."""
    _get_study(session, study_id, lang)
    hint = msg(lang, "hint.report_by_hand")
    content = await file.read(MAX_REPORT_BYTES + 1)
    if len(content) > MAX_REPORT_BYTES:
        raise HTTPException(413, msg(lang, "http.report_too_large", mb=MAX_REPORT_BYTES // 1024**2, hint=hint))
    mime_type = next((mime for magic, mime in REPORT_TYPES.items() if content.startswith(magic)), None)
    if mime_type is None:
        raise HTTPException(415, msg(lang, "http.report_bad_type"))
    file_hash = hashlib.sha256(content).hexdigest()
    cached = imaging_store.cached_report(file_hash)
    if cached is not None:
        return ReportText.model_validate(cached)
    try:
        draft = reader_factory().read(content, mime_type)
        imaging_store.save_report_and_draft(file_hash, content, draft.model_dump_json())
        return draft
    except AiNotConfigured as exc:
        raise HTTPException(503, translate_text(lang, str(exc))) from exc
    except ParseError as exc:
        raise HTTPException(502, msg(lang, "http.report_unreadable", hint=hint)) from exc
    except AiRequestError as exc:
        raise HTTPException(502, msg(lang, "http.ai_retry", error=translate_text(lang, str(exc)), hint=hint)) from exc
