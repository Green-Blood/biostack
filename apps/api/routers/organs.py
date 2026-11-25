import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from db.database import get_session
from db.models import MedicalRecord, Medication, RecordAttachment, RecordOrgan, ScanMeasurement
from services import app_settings, clock, organ_pages
from services.i18n import Lang, get_lang, msg
from services.organs import ORGANS, organ_name, param_name
from services.queries import effective_dates

router = APIRouter(tags=["organs"])


def _records(session: Session, ids: set[int]) -> list[MedicalRecord]:
    return session.exec(select(MedicalRecord).where(MedicalRecord.id.in_(ids))).all() if ids else []


@router.get("/organs/catalog")
def catalog(lang: Lang = Depends(get_lang)):
    return [{"key": o.key, "name": organ_name(o.key, lang),
             "params": [{"key": p.key, "name": param_name(p.key, lang), "kind": p.kind, "unit": p.unit, "sides": p.sides}
                        for p in o.params]} for o in ORGANS.values()]


@router.get("/organs")
def index(session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    tags = session.exec(select(RecordOrgan)).all()
    records = {r.id: r for r in _records(session, {t.record_id for t in tags})}
    rows = session.exec(select(ScanMeasurement)).all()
    dates = effective_dates(session)
    summaries = []
    for key, organ in ORGANS.items():
        scans = [records[t.record_id] for t in tags if t.organ_key == key and t.record_id in records]
        if scans:
            summaries.append(organ_pages.organ_summary(organ, lang, scans, rows, dates))
    tagged = {t.record_id for t in tags}
    unassigned = [r for r in session.exec(select(MedicalRecord).where(MedicalRecord.record_type == "imaging")) if r.id not in tagged]
    unassigned.sort(key=lambda r: (dates[r.id][0] is None, -(dates[r.id][0] or dt.date.min).toordinal(), r.id))
    return {"organs": organ_pages.sort_index(summaries),
            "unassigned": [{"record_id": r.id, "date": d.isoformat() if (d := dates[r.id][0]) else None, "title": r.title}
                           for r in unassigned]}


@router.get("/organs/{key}")
def organ_detail(key: str, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    organ = ORGANS.get(key)
    if organ is None:
        raise HTTPException(404, msg(lang, "http.organ_not_found"))
    ids = set(session.exec(select(RecordOrgan.record_id).where(RecordOrgan.organ_key == key)).all())
    records = _records(session, ids)
    rows = session.exec(select(ScanMeasurement).where(ScanMeasurement.organ_key == key)).all() if ids else []
    files = session.exec(select(RecordAttachment).where(RecordAttachment.record_id.in_(ids))
                         .order_by(RecordAttachment.id)).all() if ids else []
    meds = session.exec(select(Medication)).all()
    others = session.exec(select(MedicalRecord).where(MedicalRecord.record_type.not_in(("lab", "imaging")))).all()
    return organ_pages.organ_page(organ, lang, records, rows, files, effective_dates(session), meds, others,
                                  clock.today(app_settings.configured_zone(session)))
