"""Diagnoses, treatments, notes and files on a record. Allowed on every record, imported ones included."""
import datetime as dt
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from db.database import get_session
from db.models import Diagnosis, Medication, RecordAttachment, RecordMedication, RecordNote
from routers.records import DISPLAYABLE_IMAGES, DiagnosisIn, TreatmentIn, _today, get_or_404
from services import attachments, visits
from services.i18n import Lang, get_lang, msg

router = APIRouter(tags=["records"])
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


class DiagnosisPatch(BaseModel):
    name: str | None = None
    icd10: str | None = None
    status: str | None = None
    note: str | None = None


class TreatmentPatch(BaseModel):
    name: str | None = None
    dosage: str | None = None
    route: str | None = None
    frequency: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    notes: str | None = None


class NoteIn(BaseModel):
    text: str = ""
    date: dt.date | None = None
    kind: str | None = None


class NotePatch(BaseModel):
    text: str | None = None
    done: bool | None = None
    date: dt.date | None = None


def _one(session: Session, model, item_id: int, key: str, lang: str):
    row = session.get(model, item_id)
    if row is None:
        raise HTTPException(404, msg(lang, key))
    return row


# Diagnoses

@router.post("/records/{record_id}/diagnoses", status_code=201)
def create_diagnosis(record_id: int, body: DiagnosisIn, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    get_or_404(session, record_id, lang)
    if not body.name.strip():
        raise HTTPException(422, msg(lang, "http.diagnosis_name_required"))
    d = visits.add_diagnosis(session, record_id, body.model_dump(), lang)
    session.commit()
    session.refresh(d)
    return visits.diagnosis_out(d)


@router.patch("/diagnoses/{diagnosis_id}")
def update_diagnosis(diagnosis_id: int, body: DiagnosisPatch, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    d = _one(session, Diagnosis, diagnosis_id, "http.diagnosis_not_found", lang)
    fields = body.model_dump(exclude_unset=True)
    visits.check_diagnosis(fields.get("name"), fields.get("status"), lang)
    if "name" in fields and fields["name"] is None:
        raise HTTPException(422, msg(lang, "http.diagnosis_name_required"))
    for name, value in fields.items():
        if value is not None:
            setattr(d, name, value.strip() if name in ("name", "icd10") else value)
    session.add(d)
    session.commit()
    session.refresh(d)
    return visits.diagnosis_out(d)


@router.delete("/diagnoses/{diagnosis_id}", status_code=204)
def delete_diagnosis(diagnosis_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> None:
    session.delete(_one(session, Diagnosis, diagnosis_id, "http.diagnosis_not_found", lang))
    session.commit()


# Treatments (a treatment is a Medication row linked to the record)

def _manual_treatment(session: Session, med_id: int, lang: str) -> Medication:
    med = _one(session, Medication, med_id, "http.treatment_not_found", lang)
    if med.source != "manual":
        raise HTTPException(403, msg(lang, "http.treatment_forbidden"))
    return med


@router.post("/records/{record_id}/treatments", status_code=201)
def create_treatment(record_id: int, body: TreatmentIn, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    rec = get_or_404(session, record_id, lang)
    if not body.name.strip():
        raise HTTPException(422, msg(lang, "http.treatment_name_required"))
    med = visits.add_treatment(session, rec, rec.record_date, body.model_dump(), lang)
    session.commit()
    session.refresh(med)
    return visits.treatment_out(med, _today(session))


@router.patch("/treatments/{treatment_id}")
def update_treatment(treatment_id: int, body: TreatmentPatch, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    med = _manual_treatment(session, treatment_id, lang)
    fields = body.model_dump(exclude_unset=True)
    if "name" in fields and not (fields["name"] or "").strip():
        raise HTTPException(422, msg(lang, "http.treatment_name_required"))
    start = fields["start_date"] if "start_date" in fields else med.start_date
    end = fields["end_date"] if "end_date" in fields else med.end_date
    visits.check_treatment(None, start, end, lang)
    med.start_date, med.end_date = start, end
    for name in ("name", "dosage", "route", "frequency", "notes"):
        if fields.get(name) is not None:
            setattr(med, name, fields[name].strip() if name == "name" else fields[name])
    session.add(med)
    session.commit()
    session.refresh(med)
    return visits.treatment_out(med, _today(session))


@router.delete("/treatments/{treatment_id}", status_code=204)
def delete_treatment(treatment_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> None:
    med = _manual_treatment(session, treatment_id, lang)
    for link in session.exec(select(RecordMedication).where(RecordMedication.medication_id == med.id)):
        session.delete(link)
    session.flush()
    session.delete(med)
    session.commit()


# Notes and questions

@router.post("/records/{record_id}/notes", status_code=201)
def create_note(record_id: int, body: NoteIn, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    get_or_404(session, record_id, lang)
    n = visits.add_note(session, record_id, body.text, body.date or _today(session), body.kind, lang)
    session.commit()
    session.refresh(n)
    return visits.note_out(n)


@router.patch("/notes/{note_id}")
def update_note(note_id: int, body: NotePatch, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    n = _one(session, RecordNote, note_id, "http.note_not_found", lang)
    fields = body.model_dump(exclude_unset=True)
    if "text" in fields:
        if not (fields["text"] or "").strip():
            raise HTTPException(422, msg(lang, "http.note_text_required"))
        n.text = fields["text"].strip()
    if fields.get("done") is not None:
        n.done = fields["done"]
    if fields.get("date") is not None:
        n.note_date = fields["date"]
    session.add(n)
    session.commit()
    session.refresh(n)
    return visits.note_out(n)


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> None:
    session.delete(_one(session, RecordNote, note_id, "http.note_not_found", lang))
    session.commit()


# Files

@router.post("/records/{record_id}/attachments", status_code=201)
async def upload_attachment(record_id: int, file: UploadFile, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    get_or_404(session, record_id, lang)
    content = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(413, msg(lang, "http.attachment_too_large", mb=MAX_ATTACHMENT_BYTES // (1024 * 1024)))
    name = PurePosixPath((file.filename or "").replace("\\", "/")).name or "file"
    try:
        a = attachments.attach_bytes(session, record_id, content, name)
    except attachments.UnsupportedAttachment:
        raise HTTPException(415, msg(lang, "http.attachment_bad_type")) from None
    return {"id": a.id, "filename": a.filename, "mime_type": a.mime_type, "size_bytes": a.size_bytes,
            "is_image": a.mime_type in DISPLAYABLE_IMAGES}


@router.delete("/attachments/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> None:
    session.delete(_one(session, RecordAttachment, attachment_id, "http.attachment_not_found", lang))
    session.commit()
