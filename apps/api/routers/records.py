import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from db.database import get_session
from config import settings
from db.models import (DEMO_SOURCE, Biomarker, Clinic, Diagnosis, LabReport, MedicalRecord, Medication, RecordAttachment,
                       RecordMedication, RecordNote, RecordOrgan)
from services import app_settings, clock, visits
from services.heic import HEIC_MIME, to_jpeg
from services.i18n import Lang, get_lang, msg
from services.markers import marker_display_name
from services.organs import organ_name
from services.queries import effective_dates

router = APIRouter(tags=["records"])


DISPLAYABLE_IMAGES = {"image/jpeg", "image/png", HEIC_MIME}  # HEIC is converted to JPEG when served


def _today(session: Session) -> dt.date:
    return clock.today(app_settings.configured_zone(session))


def _record_out(rec, eff, clinics, meds, labs, attachment_count=0, diagnoses=(), today=None):
    date, suspect = eff[rec.id]
    biomarkers = labs.get(rec.id, [])
    return {
        "end_date": rec.end_date.isoformat() if rec.end_date else None, "status": rec.status,
        "stay_days": visits.stay_days(rec, date, today) if today else None, "is_manual": visits.is_manual(rec),
        "diagnoses": [d.name for d in diagnoses],
        "diagnosis_items": [{"name": d.name, "status": d.status} for d in diagnoses],
        "id": rec.id, "is_demo": rec.source == DEMO_SOURCE, "date": date.isoformat() if date else None, "date_suspect": suspect,
        "title": rec.title, "record_type": rec.record_type,
        "clinic": clinics.get(rec.clinic_id), "medications": meds.get(rec.id, []),
        "has_labs": bool(biomarkers), "out_of_range_count": sum(b.is_out_of_range for b in biomarkers),
        "details": rec.details, "doctors_note": rec.doctors_note, "attachment_count": attachment_count,
    }


def _context(session):
    clinics = {c.id: c.name for c in session.exec(select(Clinic))}
    names = {m.id: m.name for m in session.exec(select(Medication))}
    meds: dict[int, list[str]] = {}
    for link in session.exec(select(RecordMedication)):
        meds.setdefault(link.record_id, []).append(names[link.medication_id])
    labs: dict[int, list[Biomarker]] = {}
    for rep, bm in session.exec(select(LabReport, Biomarker).where(Biomarker.report_id == LabReport.id)):
        if rep.record_id:
            labs.setdefault(rep.record_id, []).append(bm)
    return clinics, meds, labs


@router.get("/records")
def list_records(session: Session = Depends(get_session), type: str | None = None, q: str | None = None,
                 from_: dt.date | None = Query(None, alias="from"), to: dt.date | None = None, lang: Lang = Depends(get_lang)):
    eff = effective_dates(session)
    clinics, meds, labs = _context(session)
    counts = dict(session.exec(select(RecordAttachment.record_id, func.count()).group_by(RecordAttachment.record_id)).all())
    diagnoses: dict[int, list[Diagnosis]] = {}
    for d in session.exec(select(Diagnosis).order_by(Diagnosis.id)):
        diagnoses.setdefault(d.record_id, []).append(d)
    tags: dict[int, list[dict]] = {}
    for t in session.exec(select(RecordOrgan).order_by(RecordOrgan.organ_key)):
        tags.setdefault(t.record_id, []).append({"key": t.organ_key, "name": organ_name(t.organ_key, lang)})
    today = _today(session)
    rows = []
    for rec in session.exec(select(MedicalRecord)):
        date = eff[rec.id][0]
        if type and rec.record_type != type:
            continue
        if from_ and (date is None or date < from_) or to and (date is None or date > to):
            continue
        if q and q.lower() not in f"{rec.title} {rec.details} {rec.doctors_note}".lower():
            continue
        rows.append({**_record_out(rec, eff, clinics, meds, labs, counts.get(rec.id, 0), diagnoses.get(rec.id, ()), today),
                     "organs": tags.get(rec.id, [])})
    dated = sorted([r for r in rows if r["date"]], key=lambda r: r["date"], reverse=True)
    return dated + [r for r in rows if not r["date"]]


def _full(session: Session, rec: MedicalRecord, lang: str) -> dict:
    eff = effective_dates(session)
    clinics, meds, labs = _context(session)
    today = _today(session)
    files = session.exec(select(RecordAttachment).where(RecordAttachment.record_id == rec.id)
                         .order_by(RecordAttachment.id)).all()
    diagnoses = session.exec(select(Diagnosis).where(Diagnosis.record_id == rec.id).order_by(Diagnosis.id)).all()
    out = _record_out(rec, eff, clinics, meds, labs, len(files), diagnoses, today)
    out["diagnoses"] = [visits.diagnosis_out(d) for d in diagnoses]
    treatments = [session.get(Medication, link.medication_id) for link in
                  session.exec(select(RecordMedication).where(RecordMedication.record_id == rec.id))]
    treatments.sort(key=lambda m: (m.start_date or dt.date.min, m.id))
    out["treatments"] = [visits.treatment_out(m, today) for m in treatments]
    notes = session.exec(select(RecordNote).where(RecordNote.record_id == rec.id)).all()
    out["notes"] = [visits.note_out(n) for n in visits.ordered_notes(notes)]
    out["department"], out["doctor_name"], out["reason"] = rec.department or "", rec.doctor_name or "", rec.reason or ""
    out["attachments"] = [{"id": f.id, "filename": f.filename, "mime_type": f.mime_type, "size_bytes": f.size_bytes,
                           "is_image": f.mime_type in DISPLAYABLE_IMAGES} for f in files]
    out["body_markdown"] = rec.body_markdown
    out["biomarkers"] = [
        {"marker_key": b.marker_key, "display_name": marker_display_name(b.marker_key, b.display_name, lang), "value": b.value,
         "result_text": b.result_text, "unit": b.unit, "ref_min": b.ref_min, "ref_max": b.ref_max,
         "out_of_range": b.is_out_of_range, "is_demo": b.source == DEMO_SOURCE} for b in labs.get(rec.id, [])]
    return out


def get_or_404(session: Session, record_id: int, lang: str) -> MedicalRecord:
    rec = session.get(MedicalRecord, record_id)
    if rec is None:
        raise HTTPException(404, msg(lang, "http.record_not_found"))
    return rec


@router.get("/records/{record_id}")
def get_record(record_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    return _full(session, get_or_404(session, record_id, lang), lang)


class DiagnosisIn(BaseModel):
    name: str = ""
    icd10: str = ""
    status: str | None = None
    note: str = ""


class TreatmentIn(BaseModel):
    name: str = ""
    dosage: str = ""
    route: str = ""
    frequency: str = ""
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    notes: str = ""


class RecordIn(BaseModel):
    record_type: str = ""
    title: str = ""
    date: dt.date | None = None
    end_date: dt.date | None = None
    status: str | None = None
    clinic_name: str = ""
    department: str = ""
    doctor_name: str = ""
    reason: str = ""
    details: str = ""
    doctors_note: str = ""
    diagnoses: list[DiagnosisIn] = []
    treatments: list[TreatmentIn] = []
    questions: list[str] = []


class RecordPatch(BaseModel):
    title: str | None = None
    record_type: str | None = None
    date: dt.date | None = None
    end_date: dt.date | None = None
    status: str | None = None
    clinic_name: str | None = None
    department: str | None = None
    doctor_name: str | None = None
    reason: str | None = None
    details: str | None = None
    doctors_note: str | None = None


class FinishIn(BaseModel):
    end_date: dt.date | None = None


@router.post("/records", status_code=201)
def create_record(body: RecordIn, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    title = visits.clean_title(body.title, lang)
    record_type = visits.check_type(body.record_type, lang)
    start = body.date or _today(session)
    status = visits.resolve_status(record_type, start, body.end_date, body.status, lang)
    for d in body.diagnoses:
        visits.check_diagnosis(d.name, d.status, lang)
        if not d.name.strip():
            raise HTTPException(422, msg(lang, "http.diagnosis_name_required"))
    for t in body.treatments:
        visits.check_treatment(t.name, t.start_date or start, t.end_date, lang)
        if not t.name.strip():
            raise HTTPException(422, msg(lang, "http.treatment_name_required"))
    if any(not q.strip() for q in body.questions):
        raise HTTPException(422, msg(lang, "http.note_text_required"))
    rec = MedicalRecord(title=title, record_type=record_type, record_date=start, end_date=body.end_date, status=status,
                        clinic_id=visits.find_or_create_clinic(session, body.clinic_name), department=body.department.strip(),
                        doctor_name=body.doctor_name.strip(), reason=body.reason.strip(), details=body.details,
                        doctors_note=body.doctors_note, source="manual", external_id=None)
    session.add(rec)
    session.flush()
    for d in body.diagnoses:
        visits.add_diagnosis(session, rec.id, d.model_dump(), lang)
    for t in body.treatments:
        visits.add_treatment(session, rec, start, t.model_dump(), lang)
    for q in body.questions:
        visits.add_note(session, rec.id, q, start, "question", lang)
    session.commit()
    session.refresh(rec)
    return _full(session, rec, lang)


@router.patch("/records/{record_id}")
def update_record(record_id: int, body: RecordPatch, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    rec = get_or_404(session, record_id, lang)
    fields = body.model_dump(exclude_unset=True)
    if not visits.is_manual(rec) and not set(fields) <= visits.IMPORTED_EDITABLE:
        raise HTTPException(403, msg(lang, "http.record_forbidden"))
    if fields.get("title") is not None or "title" in fields:
        fields["title"] = visits.clean_title(fields["title"], lang)
    record_type = visits.check_type(fields["record_type"], lang) if "record_type" in fields else rec.record_type
    start = fields["date"] if fields.get("date") is not None else rec.record_date
    end = fields["end_date"] if "end_date" in fields else rec.end_date
    if "status" in fields:
        status = visits.resolve_status(record_type, start, end, fields["status"], lang)
    elif record_type == "hospital_stay" and ("end_date" in fields or "record_type" in fields):
        status = visits.resolve_status(record_type, start, end, None, lang)
    else:
        status = visits.resolve_status(record_type, start, end, rec.status, lang) if rec.status or end else None
    rec.record_type, rec.record_date, rec.end_date, rec.status = record_type, start, end, status
    if "title" in fields:
        rec.title = fields["title"]
    if "clinic_name" in fields:
        rec.clinic_id = visits.find_or_create_clinic(session, fields["clinic_name"])
    for name in ("department", "doctor_name", "reason"):
        if fields.get(name) is not None:
            setattr(rec, name, fields[name].strip())
    for name in ("details", "doctors_note"):
        if fields.get(name) is not None:
            setattr(rec, name, fields[name])
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return _full(session, rec, lang)


@router.post("/records/{record_id}/finish")
def finish_record(record_id: int, body: FinishIn | None = None, session: Session = Depends(get_session),
                  lang: Lang = Depends(get_lang)):
    rec = get_or_404(session, record_id, lang)
    end = (body.end_date if body else None) or _today(session)
    if rec.record_date and end < rec.record_date:
        raise HTTPException(422, msg(lang, "http.record_bad_dates"))
    rec.status, rec.end_date = "completed", end
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return _full(session, rec, lang)


@router.delete("/records/{record_id}", status_code=204)
def delete_record(record_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> None:
    rec = get_or_404(session, record_id, lang)
    if not visits.is_manual(rec):
        raise HTTPException(403, msg(lang, "http.record_forbidden"))
    visits.delete_record(session, rec)


@router.get("/attachments/{attachment_id}/file")
def get_attachment_file(attachment_id: int, original: bool = False, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    attachment = session.get(RecordAttachment, attachment_id)
    path = settings.data_dir / attachment.stored_path if attachment else None
    if attachment is None or not path.is_file():
        raise HTTPException(404, msg(lang, "http.attachment_not_found"))
    if attachment.mime_type == HEIC_MIME and not original:  # `?original=true` downloads the HEIC itself
        return Response(to_jpeg(path.read_bytes()), media_type="image/jpeg", headers={"X-Content-Type-Options": "nosniff"})
    return FileResponse(path, media_type=attachment.mime_type, filename=attachment.filename,
                        content_disposition_type="inline", headers={"X-Content-Type-Options": "nosniff"})
