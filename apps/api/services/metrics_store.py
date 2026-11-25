import datetime as dt

from sqlmodel import Session, select

from db.models import DEMO_SOURCE, DailyMetric, WearableRecord
from services.health_payload import HcRecord, hc_day_totals, hc_deleted_ids, hc_records

INTEGER_FIELDS = {"steps"}


def store_hc_records(session: Session, payload: dict) -> dict[dt.date, dict[str, float]]:
    """Keep the Health Connect Webhook app's records by id and return every touched day recomputed from all its
    stored records, so a resent batch, an edit or a test send never counts anything twice."""
    days: set[dt.date] = set()
    for record_id in hc_deleted_ids(payload):
        for row in session.exec(select(WearableRecord).where(WearableRecord.key.startswith(f"{record_id}|"))).all():
            days.add(row.day)
            session.delete(row)
    for r in hc_records(payload):
        old = session.get(WearableRecord, r.key)
        if old is not None:
            days.add(old.day)
        session.merge(WearableRecord(key=r.key, day=r.day, field=r.field, value=r.value, origin=r.origin))
        days.add(r.day)
    session.flush()
    totals = {}
    for day in days:
        rows = session.exec(select(WearableRecord).where(WearableRecord.day == day)).all()
        totals[day] = hc_day_totals([HcRecord(w.key, w.field, w.day, w.value, w.origin) for w in rows])
    return {day: fields for day, fields in totals.items() if fields}


def upsert_daily_metrics(session: Session, days: dict[dt.date, dict[str, float]], source: str) -> None:
    """Write only the fields that were sent, so a partial update never blanks the rest of the day.

    A real value landing on a demo day replaces that day completely: demo and real numbers are never mixed in one row.
    """
    for day, fields in days.items():
        row = session.get(DailyMetric, day)
        if row is not None and row.source == DEMO_SOURCE and source != DEMO_SOURCE:
            session.delete(row)
            session.flush()
            row = None
        row = row or DailyMetric(metric_date=day)
        for field, value in fields.items():
            setattr(row, field, round(value) if field in INTEGER_FIELDS else value)
        row.field_sources = {**(row.field_sources or {}), **{field: source for field in fields}}
        row.source = source
        session.add(row)
    session.commit()
