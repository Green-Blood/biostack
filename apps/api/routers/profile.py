import datetime as dt

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from db.database import get_session
from db.models import BodyMeasurement
from services import body_import, clock, profile as svc
from services.range_refill import refill_ranges
from services.app_settings import configured_zone
from services.i18n import Lang, get_lang, msg

router = APIRouter(prefix="/profile", tags=["profile"])


class ProfilePatch(BaseModel):
    birth_date: dt.date | None = None
    sex: str | None = None
    height_cm: float | None = None


class MeasurementIn(BaseModel):
    date: dt.date
    kind: str
    value: float


def _measurement(m: BodyMeasurement) -> dict:
    return {"id": m.id, "date": m.measured_on.isoformat(), "kind": m.kind, "value": m.value}


@router.get("")
def read_profile(session: Session = Depends(get_session)) -> dict:
    return svc.profile_payload(session)


@router.put("")
def update_profile(body: ProfilePatch, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> dict:
    changes = {f: getattr(body, f) for f in body.model_fields_set}
    today = clock.today(configured_zone(session))
    birth = changes.get("birth_date")
    if birth is not None and (birth > today or birth.year < svc.MIN_BIRTH_YEAR):
        raise HTTPException(422, msg(lang, "http.profile_birth_date", year=svc.MIN_BIRTH_YEAR))
    if changes.get("sex") is not None and changes["sex"] not in svc.SEXES:
        raise HTTPException(422, msg(lang, "http.profile_sex"))
    height = changes.get("height_cm")
    if height is not None and not svc.HEIGHT_RANGE[0] <= height <= svc.HEIGHT_RANGE[1]:
        raise HTTPException(422, msg(lang, "http.profile_height", lo=int(svc.HEIGHT_RANGE[0]), hi=int(svc.HEIGHT_RANGE[1])))
    svc.save_profile(session, changes)
    return svc.profile_payload(session)


@router.get("/measurements")
def list_measurements(kind: str | None = Query(default=None), session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> list[dict]:
    if kind is not None and kind not in svc.KINDS:
        raise HTTPException(422, msg(lang, "http.measurement_kind"))
    query = select(BodyMeasurement).order_by(BodyMeasurement.measured_on.desc(), BodyMeasurement.id.desc())
    if kind:
        query = query.where(BodyMeasurement.kind == kind)
    return [_measurement(m) for m in session.exec(query)]


@router.post("/measurements", status_code=201)
def add_measurement(body: MeasurementIn, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> dict:
    if body.kind not in svc.KINDS:
        raise HTTPException(422, msg(lang, "http.measurement_kind"))
    lo, hi = svc.VALUE_RANGE[body.kind]
    if not lo <= body.value <= hi:
        raise HTTPException(422, msg(lang, f"http.measurement_{body.kind}_range", lo=f"{lo:g}", hi=f"{hi:g}"))
    if body.date > clock.today(configured_zone(session)):
        raise HTTPException(422, msg(lang, "http.measurement_future"))
    row = session.exec(select(BodyMeasurement).where(BodyMeasurement.measured_on == body.date, BodyMeasurement.kind == body.kind)).first()
    if row is None:
        row = BodyMeasurement(measured_on=body.date, kind=body.kind, value=body.value)
    row.value = body.value
    row.source = "manual"
    session.add(row)
    session.commit()
    session.refresh(row)
    return _measurement(row)


_TEXT_TYPES = {"", "text/csv", "text/plain", "application/csv", "application/vnd.ms-excel", "application/octet-stream", "text/tab-separated-values"}


@router.post("/measurements/import")
async def import_measurements(file: UploadFile = File(...), dry_run: bool = Query(default=True), session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> dict:
    data = await file.read(body_import.MAX_BYTES + 1)
    if len(data) > body_import.MAX_BYTES:
        raise HTTPException(413, msg(lang, "http.import_too_large"))
    name = (file.filename or "").lower()
    known_type = (file.content_type or "").split(";")[0].strip().lower() in _TEXT_TYPES or name.endswith((".csv", ".txt", ".tsv"))
    if not known_type or b"\x00" in data:
        raise HTTPException(415, msg(lang, "http.import_unsupported"))
    try:
        zone = configured_zone(session)
        result = body_import.parse_csv(data, lang, clock.today(zone), zone)
    except body_import.ImportError_ as error:
        raise HTTPException(error.status, msg(lang, error.key)) from error
    existing = svc.existing_keys(session, set(result.values))
    would_replace, would_replace_days = len(existing), len({day for day, _ in existing})
    replaced = 0
    if not dry_run:
        replaced = svc.upsert_measurements(session, result.values, "csv")
    rows, total = result.preview()
    return {
        "delimiter": result.delimiter, "encoding": result.encoding, "columns": result.columns, "day_first": result.day_first,
        "rows": rows, "total_rows": total, "imported": 0 if dry_run else len(result.values), "replaced": replaced,
        "would_replace": would_replace, "would_replace_days": would_replace_days, "replaced_days": 0 if dry_run else would_replace_days, "skipped": result.skipped, "skipped_total": result.skipped_total, "warnings": result.warnings,
    }


@router.get("/body")
def read_body(session: Session = Depends(get_session)) -> dict:
    return svc.body_summary(session)


@router.delete("/measurements/{measurement_id}", status_code=204)
def delete_measurement(measurement_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> Response:
    row = session.get(BodyMeasurement, measurement_id)
    if row is None:
        raise HTTPException(404, msg(lang, "http.measurement_not_found"))
    session.delete(row)
    session.commit()
    return Response(status_code=204)


@router.get("/bmi-history")
def read_bmi_history(session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> dict:
    return {**svc.bmi_history(session), "note": msg(lang, "profile.bmi_note")}


@router.post("/refill-ranges")
def refill_lab_ranges(session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> dict:
    """Fill the lab ranges that were blank only because the profile lacked sex or age, using the profile as it is now."""
    facts = svc.load_profile(session)
    if facts.sex is None and facts.birth_date is None:
        raise HTTPException(422, msg(lang, "http.refill_no_profile"))
    return {"filled": refill_ranges(session)}
