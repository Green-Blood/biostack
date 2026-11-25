import datetime as dt
import hashlib
from collections.abc import Callable
from typing import Literal
from functools import partial

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from config import settings
from db.database import get_session
from db.models import Biomarker, LabReport
from services import lab_store
from services.documents import SniffedDocument, sniff_document
from services.ai_provider import AiNotConfigured, build_lab_parser
from services.gemini_client import AiRequestError
from services.gemini_parser import LabParser, ParsedLab, ParseError
from services.i18n import Lang, get_lang, msg, translate_text
from services.lab_rows import ReviewedRow
from services.lab_text_parser import extract_pdf_text, parse_lab_text
from services.markers import known_marker_names, marker_display_name

router = APIRouter(prefix="/labs", tags=["lab uploads"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
HASH_PATTERN = r"^[0-9a-f]{64}$"


class UploadDraft(ParsedLab):
    file_hash: str
    method: Literal["text", "ai"] = "ai"  # "text": read from the PDF's own text, nothing was sent to the AI


class ManualSubmission(BaseModel):
    test_date: dt.date
    lab_name: str = ""
    rows: list[ReviewedRow] = Field(min_length=1)


class PdfSubmission(ManualSubmission):
    file_hash: str = Field(pattern=HASH_PATTERN)


def get_lab_parser_factory() -> Callable[[], LabParser]:
    return partial(build_lab_parser, settings)


async def _read_document(file: UploadFile, lang: Lang) -> tuple[bytes, SniffedDocument]:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, msg(lang, "http.lab_too_large", mb=MAX_UPLOAD_BYTES // (1024 * 1024)))
    kind = sniff_document(content)
    if kind is None:
        raise HTTPException(415, msg(lang, "http.lab_bad_type"))
    return content, kind


def _saved(session: Session, report_id: int, created: bool, lang: Lang) -> dict:
    markers = {(b.marker_key, b.display_name) for b in
               session.exec(select(Biomarker).where(Biomarker.report_id == report_id))}
    return {"report_id": report_id, "created": created,
            "markers": [{"marker_key": k, "display_name": marker_display_name(k, n, lang)}
                        for k, n in sorted(markers, key=lambda m: marker_display_name(m[0], m[1], lang).lower())]}


@router.get("/marker-names")
def marker_names() -> list[str]:
    return known_marker_names()


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...), session: Session = Depends(get_session),
                     parser_factory: Callable[[], LabParser] = Depends(get_lab_parser_factory),
                     lang: Lang = Depends(get_lang)) -> UploadDraft:
    content, kind = await _read_document(file, lang)
    file_hash = hashlib.sha256(content).hexdigest()
    existing = lab_store.find_report_by_hash(session, file_hash)
    if existing is not None:
        raise HTTPException(409, {"message": msg(lang, "http.lab_already_saved"), "report_id": existing.id})
    cached = lab_store.read_cached_draft(file_hash)
    if cached is not None:
        return _localized(UploadDraft.model_validate(cached), lang)
    parsed = parse_lab_text(extract_pdf_text(content), session) if kind.mime_type == "application/pdf" else None
    method = "text"
    if parsed is None:
        method = "ai"
        parsed = _parse_with_ai(parser_factory, content, session, kind, lang)
    draft = UploadDraft(file_hash=file_hash, method=method, **parsed.model_dump())
    lab_store.save_pdf_and_draft(file_hash, content, kind.extension, draft.model_dump_json())
    return _localized(draft, lang)


def _localized(draft: UploadDraft, lang: Lang) -> UploadDraft:
    """The draft as stored keeps catalog names in English; the person sees them in their language."""
    rows = [row.model_copy(update={"display_name": marker_display_name(row.marker_key, row.display_name, lang)})
            for row in draft.rows]
    return draft.model_copy(update={"rows": rows})


def _parse_with_ai(parser_factory: Callable[[], LabParser], content: bytes, session: Session,
                   kind: SniffedDocument, lang: Lang) -> ParsedLab:
    try:
        return parser_factory().parse(content, session, kind.mime_type)
    except AiNotConfigured as exc:
        raise HTTPException(503, translate_text(lang, str(exc))) from exc
    except ParseError as exc:
        raise HTTPException(502, msg(lang, "http.lab_unreadable", hint=msg(lang, "hint.lab_by_hand"))) from exc
    except AiRequestError as exc:
        raise HTTPException(502, msg(lang, "http.ai_retry", error=translate_text(lang, str(exc)), hint=msg(lang, "hint.lab_by_hand"))) from exc


@router.post("/confirm", status_code=201)
def confirm_pdf(body: PdfSubmission, response: Response, session: Session = Depends(get_session),
                lang: Lang = Depends(get_lang)) -> dict:
    existing = lab_store.find_report_by_hash(session, body.file_hash)
    if existing is not None:
        response.status_code = 200
        return _saved(session, existing.id, created=False, lang=lang)
    if lab_store.pdf_file(body.file_hash) is None:
        raise HTTPException(404, msg(lang, "http.lab_upload_first"))
    report = lab_store.save_report(session, test_date=body.test_date, lab_name=body.lab_name, rows=body.rows,
                                   source="pdf", file_hash=body.file_hash)
    return _saved(session, report.id, created=True, lang=lang)


@router.post("/manual", status_code=201)
def add_manual(body: ManualSubmission, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> dict:
    report = lab_store.save_report(session, test_date=body.test_date, lab_name=body.lab_name, rows=body.rows,
                                   source="manual")
    return _saved(session, report.id, created=True, lang=lang)


@router.delete("/{report_id}", status_code=204)
def delete_report(report_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> Response:
    report = session.get(LabReport, report_id)
    if report is None:
        raise HTTPException(404, msg(lang, "http.lab_not_found"))
    if report.source not in lab_store.EDITABLE_SOURCES:
        raise HTTPException(403, msg(lang, "http.lab_delete_forbidden"))
    lab_store.delete_report(session, report)
    return Response(status_code=204)
