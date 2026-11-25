"""Visits and hospital stays: diagnoses, treatments, daily notes and questions."""
import datetime as dt

from fastapi import HTTPException
from sqlmodel import Session, select

from db.models import (Clinic, DateReview, Diagnosis, LabReport, MedicalRecord, Medication, RecordAttachment,
                       RecordMedication, RecordNote)
from services.courses import course_status
from services import scan_store
from services.i18n import msg

RECORD_TYPES = ("visit", "hospital_stay", "procedure", "lab", "imaging", "other")
STATUSES = ("ongoing", "completed")
DIAGNOSIS_STATUSES = ("suspected", "confirmed", "ruled_out")
NOTE_KINDS = ("note", "question")
IMPORTED_EDITABLE = {"department", "doctor_name", "reason", "doctors_note", "status", "end_date"}
MAX_TITLE = 200


def is_manual(rec: MedicalRecord) -> bool:
    return rec.source == "manual"


def clean_title(title: str | None, lang: str) -> str:
    title = (title or "").strip()
    if not title:
        raise HTTPException(422, msg(lang, "http.record_title_required"))
    if len(title) > MAX_TITLE:
        raise HTTPException(422, msg(lang, "http.record_title_too_long"))
    return title


def check_type(record_type: str | None, lang: str) -> str:
    if record_type not in RECORD_TYPES:
        raise HTTPException(422, msg(lang, "http.record_bad_type"))
    return record_type


def resolve_status(record_type: str, start: dt.date | None, end: dt.date | None, status: str | None, lang: str) -> str | None:
    """Validate the dates and status of a record and return the status to store."""
    if end is not None and start is not None and end < start:
        raise HTTPException(422, msg(lang, "http.record_bad_dates"))
    if status is not None and status not in STATUSES:
        raise HTTPException(422, msg(lang, "http.record_bad_status"))
    if status == "completed" and end is None:
        raise HTTPException(422, msg(lang, "http.record_completed_needs_end"))
    if status is None and record_type == "hospital_stay":
        return "completed" if end is not None else "ongoing"
    return status


def find_or_create_clinic(session: Session, name: str | None) -> int | None:
    name = (name or "").strip()
    if not name:
        return None
    for clinic in session.exec(select(Clinic)):
        if clinic.name.strip().casefold() == name.casefold():
            return clinic.id
    clinic = Clinic(name=name, source="manual")
    session.add(clinic)
    session.flush()
    return clinic.id


def stay_days(rec: MedicalRecord, date: dt.date | None, today: dt.date) -> int | None:
    if rec.record_type != "hospital_stay" or date is None:
        return None
    end = rec.end_date or today
    return max((end - date).days + 1, 0)


def treatment_out(med: Medication, today: dt.date) -> dict:
    return {"id": med.id, "name": med.name, "dosage": med.dosage, "route": med.route or "", "frequency": med.frequency or "",
            "start_date": med.start_date.isoformat() if med.start_date else None,
            "end_date": med.end_date.isoformat() if med.end_date else None, "notes": med.notes,
            "status": course_status(med, today), "editable": med.source == "manual"}


def diagnosis_out(d: Diagnosis) -> dict:
    return {"id": d.id, "name": d.name, "icd10": d.icd10, "status": d.status, "note": d.note}


def note_out(n: RecordNote) -> dict:
    return {"id": n.id, "date": n.note_date.isoformat(), "text": n.text, "kind": n.kind, "done": n.done}


def ordered_notes(notes: list[RecordNote]) -> list[RecordNote]:
    plain = sorted((n for n in notes if n.kind != "question"), key=lambda n: (n.note_date, n.id), reverse=True)
    return plain + sorted((n for n in notes if n.kind == "question"), key=lambda n: n.id)


def check_diagnosis(name: str | None, status: str | None, lang: str) -> None:
    if name is not None and not name.strip():
        raise HTTPException(422, msg(lang, "http.diagnosis_name_required"))
    if status is not None and status not in DIAGNOSIS_STATUSES:
        raise HTTPException(422, msg(lang, "http.diagnosis_bad_status"))


def add_diagnosis(session: Session, record_id: int, data: dict, lang: str) -> Diagnosis:
    check_diagnosis(data.get("name") or "", data.get("status"), lang)
    d = Diagnosis(record_id=record_id, name=data["name"].strip(), icd10=(data.get("icd10") or "").strip(),
                  status=data.get("status") or "suspected", note=data.get("note") or "")
    session.add(d)
    return d


def check_treatment(name: str | None, start: dt.date | None, end: dt.date | None, lang: str) -> None:
    if name is not None and not name.strip():
        raise HTTPException(422, msg(lang, "http.treatment_name_required"))
    if start and end and end < start:
        raise HTTPException(422, msg(lang, "http.treatment_bad_dates"))


def add_treatment(session: Session, rec: MedicalRecord, record_date: dt.date | None, data: dict, lang: str) -> Medication:
    start = data.get("start_date") or record_date
    check_treatment(data.get("name") or "", start, data.get("end_date"), lang)
    med = Medication(name=data["name"].strip(), dosage=data.get("dosage") or "", route=data.get("route") or None,
                     frequency=data.get("frequency") or None, start_date=start, end_date=data.get("end_date"),
                     notes=data.get("notes") or "", source="manual")
    session.add(med)
    session.flush()
    session.add(RecordMedication(record_id=rec.id, medication_id=med.id))
    return med


def add_note(session: Session, record_id: int, text: str | None, date: dt.date, kind: str | None, lang: str) -> RecordNote:
    if not (text or "").strip():
        raise HTTPException(422, msg(lang, "http.note_text_required"))
    if kind is not None and kind not in NOTE_KINDS:
        raise HTTPException(422, msg(lang, "http.note_bad_kind"))
    n = RecordNote(record_id=record_id, note_date=date, text=text.strip(), kind=kind or "note")
    session.add(n)
    return n


def delete_record(session: Session, rec: MedicalRecord) -> None:
    """Remove a manual record with its diagnoses, notes, links, attachment rows (stored files stay, they may be shared)
    and the treatments no other record links."""
    rid = rec.id
    scan_store.delete_for_record(session, rid)
    for model in (Diagnosis, RecordNote, RecordAttachment):
        for row in session.exec(select(model).where(model.record_id == rid)):
            session.delete(row)
    links = session.exec(select(RecordMedication).where(RecordMedication.record_id == rid)).all()
    for link in links:
        session.delete(link)
    session.flush()
    for link in links:
        med = session.get(Medication, link.medication_id)
        shared = session.exec(select(RecordMedication).where(RecordMedication.medication_id == link.medication_id)).first()
        if med is not None and med.source == "manual" and shared is None:
            session.delete(med)
    for rep in session.exec(select(LabReport).where(LabReport.record_id == rid)):
        rep.record_id = None
        session.add(rep)
    review = session.get(DateReview, rid)
    if review is not None:
        session.delete(review)
    session.delete(rec)
    session.commit()
