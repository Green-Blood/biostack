"""Organ tags and measurements of a record: extraction merge rules and the owner's review.
Rows the owner has reviewed (verified) or written (origin "manual") are never overwritten by an extraction."""
import logging
import math
from dataclasses import dataclass, field

from pydantic import BaseModel
from sqlmodel import Session, select

from config import settings
from db.models import MedicalRecord, RecordAttachment, RecordOrgan, ScanMeasurement
from services.lab_text_parser import extract_pdf_text
from services.organs import ORGANS, ORIGINS, SIDES, get_param
from services.scan_extractor import Extraction, Measurement, extract_rule

log = logging.getLogger(__name__)
MAX_VALUE = 100000
MAX_TEXT = 200
AI_MIME_TYPES = ("application/pdf", "image/png", "image/jpeg")


class ScanInvalid(ValueError):
    """A submitted organ or measurement is not valid; `key` is the i18n message key."""

    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


class MeasurementIn(BaseModel):
    organ_key: str
    param_key: str
    side: str = ""
    value: float | None = None
    value_text: str | None = None


@dataclass
class ApplyReport:
    added: int = 0
    updated: int = 0
    skipped_verified: int = 0
    organs_added: list[str] = field(default_factory=list)


def _check_origin(origin: str) -> None:
    if origin not in ORIGINS:
        raise ValueError(f"origin must be one of {ORIGINS}")


def validate_measurement(organ_key: str, param_key: str, side: str, value: float | None, value_text: str | None):
    """The catalog param when the row is valid, else raises ScanInvalid."""
    if organ_key not in ORGANS:
        raise ScanInvalid("http.scan_bad_organ")
    param = get_param(organ_key, param_key)
    if param is None:
        raise ScanInvalid("http.scan_bad_param")
    if side not in SIDES or (side != "") != param.sides:
        raise ScanInvalid("http.scan_bad_side")
    if param.kind == "numeric":
        if value is None or value_text is not None or not math.isfinite(value) or not 0 <= value <= MAX_VALUE:
            raise ScanInvalid("http.scan_bad_value")
    elif value is not None or not (value_text or "").strip() or len(value_text.strip()) > MAX_TEXT:
        raise ScanInvalid("http.scan_bad_value")
    return param


def _pdf_text(session: Session, record_id: int) -> list[str]:
    out = []
    for att in session.exec(select(RecordAttachment).where(RecordAttachment.record_id == record_id)
                            .order_by(RecordAttachment.id)):
        if att.mime_type != "application/pdf":
            continue
        try:
            out.append(extract_pdf_text((settings.data_dir / att.stored_path).read_bytes()))
        except Exception:  # a missing or unreadable file only means less text
            log.info("attachment %s could not be read", att.id)
    return out


def record_text(session: Session, record: MedicalRecord) -> str:
    parts = [record.details, record.doctors_note, record.body_markdown, *_pdf_text(session, record.id)]
    return "\n".join(p for p in parts if p)


def _tag(session: Session, record_id: int, organ: str, origin: str, report: ApplyReport) -> None:
    if session.get(RecordOrgan, (record_id, organ)) is None:
        session.add(RecordOrgan(record_id=record_id, organ_key=organ, origin=origin))
        report.organs_added.append(organ)


def apply_extraction(session: Session, record_id: int, extraction: Extraction, origin: str) -> ApplyReport:
    _check_origin(origin)
    report = ApplyReport()
    existing = {(r.organ_key, r.param_key, r.side): r for r in session.exec(
        select(ScanMeasurement).where(ScanMeasurement.record_id == record_id))}
    seen_organs = list(extraction.organs)
    for m in extraction.measurements:
        try:
            param = validate_measurement(m.organ_key, m.param_key, m.side, m.value, m.value_text)
        except ScanInvalid:
            continue  # the catalog is the contract; a row outside it is dropped
        if m.organ_key not in seen_organs:
            seen_organs.append(m.organ_key)
        row = existing.get((m.organ_key, m.param_key, m.side))
        if row is None:
            row = ScanMeasurement(record_id=record_id, organ_key=m.organ_key, param_key=m.param_key, side=m.side,
                                  value=m.value, value_text=m.value_text, unit=param.unit, origin=origin, verified=False)
            session.add(row)
            existing[(m.organ_key, m.param_key, m.side)] = row
            report.added += 1
        elif row.origin == "manual" or row.verified:
            report.skipped_verified += 1
        elif (row.value, row.value_text) != (m.value, m.value_text):
            row.value, row.value_text, row.unit, row.origin = m.value, m.value_text, param.unit, origin
            session.add(row)
            report.updated += 1
    for organ in seen_organs:
        if organ in ORGANS:
            _tag(session, record_id, organ, origin, report)
    session.commit()
    return report


def run_rule_extraction(session: Session, record_id: int) -> ApplyReport:
    record = session.get(MedicalRecord, record_id)
    return apply_extraction(session, record_id, extract_rule(record.title, record_text(session, record)), "rule")


def replace_review(session: Session, record_id: int, organs: list[str], measurements: list[MeasurementIn]) -> None:
    """The owner's review replaces tags and rows; everything submitted is verified."""
    params = {}
    keys = set()
    for organ in organs:
        if organ not in ORGANS:
            raise ScanInvalid("http.scan_bad_organ")
    for m in measurements:
        if m.value_text is not None:
            m.value_text = m.value_text.strip()
        params[id(m)] = validate_measurement(m.organ_key, m.param_key, m.side, m.value, m.value_text)
        key = (m.organ_key, m.param_key, m.side)
        if key in keys:
            raise ScanInvalid("http.scan_bad_value")
        keys.add(key)
    old_rows = {(r.organ_key, r.param_key, r.side): r for r in session.exec(
        select(ScanMeasurement).where(ScanMeasurement.record_id == record_id))}
    old_tags = {t.organ_key: t for t in session.exec(select(RecordOrgan).where(RecordOrgan.record_id == record_id))}
    for row in old_rows.values():
        session.delete(row)
    for tag in old_tags.values():
        session.delete(tag)
    session.flush()
    for m in measurements:
        old = old_rows.get((m.organ_key, m.param_key, m.side))
        origin = old.origin if old is not None and (old.value, old.value_text) == (m.value, m.value_text) else "manual"
        session.add(ScanMeasurement(record_id=record_id, organ_key=m.organ_key, param_key=m.param_key, side=m.side,
                                    value=m.value, value_text=m.value_text, unit=params[id(m)].unit,
                                    origin=origin, verified=True))
    for organ in dict.fromkeys([*organs, *(m.organ_key for m in measurements)]):
        session.add(RecordOrgan(record_id=record_id, organ_key=organ,
                                origin=old_tags[organ].origin if organ in old_tags else "manual"))
    session.commit()


def delete_for_record(session: Session, record_id: int) -> None:
    for model in (ScanMeasurement, RecordOrgan):
        for row in session.exec(select(model).where(model.record_id == record_id)):
            session.delete(row)
    session.flush()


def backfill(session: Session) -> dict:
    """Rule extraction for every imaging record that has no tags and no measurements yet."""
    touched = {r for r in session.exec(select(RecordOrgan.record_id))} | {
        r for r in session.exec(select(ScanMeasurement.record_id))}
    out = {"records": 0, "tagged": 0, "measurements": 0, "untagged": [], "errors": []}
    for rec in session.exec(select(MedicalRecord).where(MedicalRecord.record_type == "imaging").order_by(MedicalRecord.id)).all():
        rid = rec.id
        if rid in touched:
            continue
        try:
            report = run_rule_extraction(session, rid)
        except Exception:  # one unreadable record must not stop the run
            session.rollback()
            log.exception("backfill failed for record %s", rid)
            out["errors"].append(rid)
            continue
        out["records"] += 1
        out["measurements"] += report.added
        if report.organs_added:
            out["tagged"] += 1
        else:
            out["untagged"].append(rid)
    return out


def run_ai_extraction(session: Session, record_id: int, extractor) -> ApplyReport:
    """AI reading for the parameters the rules (or the owner) have not already filled; the model's text is the
    report text when there is one, otherwise the record's first PDF or photo attachment."""
    record = session.get(MedicalRecord, record_id)
    text = record_text(session, record)
    document, mime_type = (None, None) if text.strip() else _first_attachment(session, record_id)
    if not text.strip() and document is None:
        return ApplyReport()
    extraction = extractor.extract(record.title, text, document, mime_type)
    have = {(r.organ_key, r.param_key, r.side) for r in session.exec(
        select(ScanMeasurement).where(ScanMeasurement.record_id == record_id))}
    rest = [m for m in extraction.measurements if (m.organ_key, m.param_key, m.side) not in have]
    return apply_extraction(session, record_id, Extraction(organs=extraction.organs, measurements=rest), "ai")


def _first_attachment(session: Session, record_id: int) -> tuple[bytes | None, str | None]:
    for att in session.exec(select(RecordAttachment).where(RecordAttachment.record_id == record_id)
                            .order_by(RecordAttachment.id)):
        if att.mime_type not in AI_MIME_TYPES:
            continue
        try:
            return (settings.data_dir / att.stored_path).read_bytes(), att.mime_type
        except OSError:
            log.info("attachment %s could not be read", att.id)
    return None, None
