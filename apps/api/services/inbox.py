"""The files inbox: sort an uploaded file by what it contains (no AI), and file a confirmed batch under records."""
import datetime as dt
import logging
import re
from typing import Any

from pydantic import ValidationError
from sqlmodel import Session, select

from db.models import Biomarker, LabReport, MarkerTier, MedicalRecord, RecordAttachment
from services import lab_store
from services.attachments import UnsupportedAttachment, attach_file
from services.i18n import msg
from services.lab_rows import ReviewedRow
from services.scan_store import run_rule_extraction

log = logging.getLogger(__name__)

NEAR_DAYS = 14
KINDS = ("lab", "imaging_report", "other")
_IMAGING_WORDS = re.compile(r"\bМРТ\b|\bКТ\b|\bУЗИ\b|рентген|заключени|\bMRI\b|\bCT\b|ultrasound|x-ray|impression", re.I)
_RECORD_TYPE = {"lab": "lab", "imaging_report": "imaging", "other": "other"}


def classify_text(text: str, has_table: bool) -> str:
    if has_table:
        return "lab"
    return "imaging_report" if _IMAGING_WORDS.search(text or "") else "other"


def record_summary(record: MedicalRecord) -> dict:
    return {"id": record.id, "title": record.title, "date": record.record_date.isoformat() if record.record_date else None}


def suggest_record(session: Session, file_hash: str, test_date: dt.date | None) -> dict | None:
    """The record the file is already attached to, else the record dated closest to `test_date` within 14 days."""
    attached = session.exec(select(RecordAttachment).where(RecordAttachment.sha256 == file_hash)).first()
    if attached is not None:
        record = session.get(MedicalRecord, attached.record_id)
        if record is not None:
            return record_summary(record)
    if test_date is None:
        return None
    window = dt.timedelta(days=NEAR_DAYS)
    candidates = session.exec(select(MedicalRecord).where(
        MedicalRecord.record_date >= test_date - window, MedicalRecord.record_date <= test_date + window)).all()
    if not candidates:
        return None
    return record_summary(min(candidates, key=lambda r: (abs((r.record_date - test_date).days), r.id)))


def _title(item: dict, lang: str, date: dt.date | None) -> str:
    given = (item.get("title") or "").strip()
    if given:
        return given
    key = {"lab": "inbox.title_lab", "imaging_report": "inbox.title_imaging"}.get(item["kind"], "inbox.title_other")
    return msg(lang, key, date=date.isoformat() if date else "").strip()


def _rows(raw: list[dict] | None) -> list[ReviewedRow]:
    return [ReviewedRow.model_validate(row) for row in (raw or [])]


def _save_item(session: Session, item: dict, lang: str) -> dict:
    file_hash, kind = item.get("file_hash", ""), item.get("kind")
    result: dict[str, Any] = {"file_hash": file_hash, "status": "error", "record_id": None, "report_id": None, "message": None}
    if kind not in KINDS:
        result["message"] = msg(lang, "inbox.item_bad_kind")
        return result
    stored = lab_store.pdf_file(file_hash) if re.fullmatch(r"[0-9a-f]{64}", file_hash or "") else None
    if stored is None:
        result["message"] = msg(lang, "inbox.item_no_file")
        return result
    test_date = item.get("test_date")
    test_date = dt.date.fromisoformat(test_date) if isinstance(test_date, str) and test_date else test_date
    rows: list[ReviewedRow] = []
    existing_report = lab_store.find_report_by_hash(session, file_hash) if kind == "lab" else None
    if kind == "lab" and existing_report is None:
        if test_date is None:
            result["message"] = msg(lang, "inbox.item_lab_needs_date")
            return result
        try:
            rows = _rows(item.get("rows"))
        except ValidationError as exc:
            result["message"] = msg(lang, "inbox.item_bad_rows", error=exc.errors()[0]["msg"].removeprefix("Value error, "))
            return result
        if not rows:
            result["message"] = msg(lang, "inbox.item_lab_needs_rows")
            return result
    record_id = item.get("record_id") or (existing_report.record_id if existing_report else None)
    created_record: MedicalRecord | None = None
    report: LabReport | None = None
    try:
        if record_id is not None and session.get(MedicalRecord, record_id) is None:
            result["message"] = msg(lang, "inbox.item_no_record")
            return result
        if record_id is None:
            created_record = MedicalRecord(title=_title(item, lang, test_date), record_type=_RECORD_TYPE[kind],
                                           record_date=test_date, source="manual")
            session.add(created_record)
            session.commit()
            session.refresh(created_record)
            record_id = created_record.id
        if kind == "lab":
            if existing_report is None:
                report = lab_store.save_report(session, test_date=test_date, lab_name=item.get("lab_name") or "", rows=rows,
                                               source="pdf", file_hash=file_hash, record_id=record_id)
            else:
                report = existing_report
                if report.record_id is None:
                    report.record_id = record_id
                    session.add(report)
                    session.commit()
        attachment = attach_file(session, record_id, stored)
        name = (item.get("filename") or "").strip()
        if name and attachment.filename != name:
            attachment.filename = name[:255]
            session.add(attachment)
            session.commit()
    except (UnsupportedAttachment, OSError) as exc:  # roll this item back; other items are untouched
        session.rollback()
        if report is not None and existing_report is None:
            for stale in (*session.exec(select(Biomarker).where(Biomarker.report_id == report.id)),
                          *session.exec(select(MarkerTier).where(MarkerTier.report_id == report.id))):
                session.delete(stale)
            session.delete(report)
        if created_record is not None:
            session.delete(created_record)
        session.commit()
        result["message"] = str(exc)
        return result
    target = session.get(MedicalRecord, record_id)
    if kind == "imaging_report" and target is not None and target.record_type == "imaging":  # never tag a visit
        try:
            run_rule_extraction(session, record_id)
        except Exception:  # reading organ measurements is a bonus; it never fails the save
            session.rollback()
            log.warning("organ extraction failed for record %s", record_id, exc_info=True)
    result.update(status="already_saved" if existing_report is not None else "saved", record_id=record_id,
                  report_id=report.id if report else None)
    return result


def confirm_batch(session: Session, items: list[dict], lang: str) -> list[dict]:
    return [_save_item(session, item, lang) for item in items]
