import datetime as dt
import hashlib

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session

from db.database import get_session
from routers.lab_uploads import UploadDraft, _localized, _read_document
from services import inbox, lab_store
from services.i18n import Lang, get_lang
from services.lab_text_parser import extract_pdf_text, parse_lab_text

router = APIRouter(prefix="/inbox", tags=["inbox"])


class AnalyzedFile(BaseModel):
    file_hash: str
    filename: str
    kind: str  # lab | imaging_report | other
    needs_ai: bool
    draft: UploadDraft | None = None
    already_saved: dict | None = None
    suggested_record: dict | None = None


class ConfirmItem(BaseModel):
    file_hash: str
    kind: str
    filename: str | None = None
    test_date: dt.date | None = None
    lab_name: str = ""
    rows: list[dict] = Field(default_factory=list)  # validated per item, so one bad row cannot sink the batch
    record_id: int | None = None
    title: str | None = None


class ConfirmBatch(BaseModel):
    items: list[ConfirmItem]


@router.post("/analyze")
async def analyze(file: UploadFile = File(...), session: Session = Depends(get_session),
                  lang: Lang = Depends(get_lang)) -> AnalyzedFile:
    content, doc = await _read_document(file, lang)
    file_hash = hashlib.sha256(content).hexdigest()
    name = file.filename or f"{file_hash[:8]}{doc.extension}"
    existing = lab_store.find_report_by_hash(session, file_hash)
    cached = lab_store.read_cached_draft(file_hash)
    draft = UploadDraft.model_validate(cached) if cached is not None else None
    kind, needs_ai = "other", False
    if existing is not None:
        kind = "lab"
    elif draft is not None:
        kind = "lab"
    elif doc.mime_type != "application/pdf":
        needs_ai = True
    else:
        text = extract_pdf_text(content)
        parsed = parse_lab_text(text, session)
        if parsed is not None:
            draft = UploadDraft(file_hash=file_hash, method="text", **parsed.model_dump())
            kind = "lab"
        elif not text.strip():
            needs_ai = True
        else:
            kind = inbox.classify_text(text, has_table=False)
    if lab_store.pdf_file(file_hash) is None:
        if draft is not None and cached is None:
            lab_store.save_pdf_and_draft(file_hash, content, doc.extension, draft.model_dump_json())
        else:
            lab_store.store_original(file_hash, content, doc.extension)
    return AnalyzedFile(
        file_hash=file_hash, filename=name, kind=kind, needs_ai=needs_ai,
        draft=_localized(draft, lang) if draft is not None else None,
        already_saved={"report_id": existing.id} if existing is not None else None,
        suggested_record=inbox.suggest_record(session, file_hash, draft.test_date if draft else None))


@router.post("/confirm")
def confirm(body: ConfirmBatch, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> dict:
    return {"results": inbox.confirm_batch(session, [i.model_dump() for i in body.items], lang)}
