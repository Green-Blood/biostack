"""Organ pages: pure functions that shape already-loaded rows into the organ index and organ page data.
The router loads everything with a fixed number of queries; nothing here touches the database."""
import datetime as dt
from collections import defaultdict
from collections.abc import Iterable

from db.models import MedicalRecord, Medication, RecordAttachment, ScanMeasurement
from services.organs import ORGANS, Organ, Param, organ_name, param_name

SIDE_ORDER = {"": 0, "left": 1, "right": 2}
Dates = dict[int, tuple[dt.date | None, bool]]


def series_key(param_key: str, side: str) -> str:
    return f"{param_key}:{side}" if side else param_key


def change_between(prev: float | str, cur: float | str) -> dict:
    """How a value moved since the previous scan that had it. Text values only say changed/same."""
    if isinstance(prev, str) or isinstance(cur, str):
        same = str(prev).strip().casefold() == str(cur).strip().casefold()
        return {"delta": None, "pct": None, "direction": "same" if same else "changed"}
    raw = cur - prev
    delta = round(raw, 4)
    pct = round(raw / abs(prev) * 100, 1) if prev else None
    return {"delta": delta, "pct": pct, "direction": "up" if delta > 0 else "down" if delta < 0 else "same"}


def _scan_order(rec: MedicalRecord, dates: Dates) -> tuple:
    d = dates[rec.id][0]
    return (d is None, d or dt.date.min, rec.id)


def _value(m: ScanMeasurement) -> float | str | None:
    return m.value if m.value is not None else m.value_text


def _present_params(organ: Organ, rows: Iterable[ScanMeasurement]) -> list[tuple[Param, str]]:
    """(param, side) pairs that have a value, in catalog order, sides left then right."""
    have = {(m.param_key, m.side) for m in rows if _value(m) is not None}
    return [(p, side) for p in organ.params for side in sorted((s for k, s in have if k == p.key), key=lambda s: SIDE_ORDER.get(s, 9))]


def organ_page(organ: Organ, lang: str, records: list[MedicalRecord], measurements: list[ScanMeasurement],
               attachments: list[RecordAttachment], dates: Dates, medications: list[Medication],
               other_records: list[MedicalRecord], today: dt.date) -> dict:
    records = sorted(records, key=lambda r: _scan_order(r, dates))
    rows = [m for m in measurements if m.organ_key == organ.key]
    by_record: dict[int, list[ScanMeasurement]] = defaultdict(list)
    for m in rows:
        by_record[m.record_id].append(m)
    files: dict[int, list[dict]] = defaultdict(list)
    for a in attachments:
        files[a.record_id].append({"id": a.id, "filename": a.filename, "mime_type": a.mime_type})
    present = _present_params(organ, rows)

    last: dict[str, float | str] = {}
    scans, points = [], defaultdict(list)
    for rec in records:
        date, suspect = dates[rec.id]
        mine = {(m.param_key, m.side): m for m in by_record.get(rec.id, [])}
        values = {}
        for param, side in present:
            m = mine.get((param.key, side))
            if m is None or _value(m) is None:
                continue
            key, cur = series_key(param.key, side), _value(m)
            values[key] = {"value": m.value, "value_text": m.value_text, "unit": m.unit, "origin": m.origin,
                           "verified": m.verified, "change": change_between(last[key], cur) if key in last else None}
            last[key] = cur
            if date is not None and param.kind == "numeric" and param.chart:
                points[key].append({"record_id": rec.id, "date": date.isoformat(), "value": m.value})
        scans.append({"record_id": rec.id, "date": date.isoformat() if date else None, "date_suspect": suspect,
                      "title": rec.title, "details": rec.details, "doctors_note": rec.doctors_note,
                      "body_markdown": rec.body_markdown, "attachments": files.get(rec.id, []),
                      "has_numbers": any(m.value is not None for m in by_record.get(rec.id, [])), "values": values})

    dated = [dates[r.id][0] for r in records if dates[r.id][0] is not None]
    treatments, visits = [], []
    if dated:
        lo = dated[0]
        for med in medications:
            if med.start_date and med.start_date <= today and (med.end_date or today) >= lo:
                treatments.append({"name": med.name, "dosage": med.dosage, "start": med.start_date.isoformat(),
                                   "end": med.end_date.isoformat() if med.end_date else None,
                                   "related": med.target_marker_key in organ.related_markers})
        treatments.sort(key=lambda t: (t["start"], t["name"]))
        for rec in other_records:
            d = dates[rec.id][0]
            if d is not None and lo <= d <= today:
                visits.append({"id": rec.id, "date": d.isoformat(), "title": rec.title, "record_type": rec.record_type})
        visits.sort(key=lambda v: (v["date"], v["id"]))
    return {
        "key": organ.key, "name": organ_name(organ.key, lang), "aliases": list(organ.aliases),
        "related_marker_keys": list(organ.related_markers),
        "params": [{"series_key": series_key(p.key, s), "param_key": p.key, "side": s, "name": param_name(p.key, lang),
                    "unit": p.unit, "kind": p.kind, "chart": p.chart and p.kind == "numeric",
                    "headline": (p.key, s) == organ.headline} for p, s in present],
        "scans": scans,
        "series": [{"series_key": series_key(p.key, s), "name": param_name(p.key, lang), "unit": p.unit,
                    "points": points[series_key(p.key, s)]}
                   for p, s in present if series_key(p.key, s) in points],
        "treatments": treatments, "visits": visits,
    }


def organ_summary(organ: Organ, lang: str, records: list[MedicalRecord], measurements: list[ScanMeasurement],
                  dates: Dates) -> dict:
    records = sorted(records, key=lambda r: _scan_order(r, dates))
    rows = [m for m in measurements if m.organ_key == organ.key]
    param_key, side = organ.headline
    param = next(p for p in organ.params if p.key == param_key)
    value_of = {m.record_id: m.value for m in rows
                if m.param_key == param_key and m.side == side and m.value is not None}
    pts = [value_of[r.id] for r in records if r.id in value_of and dates[r.id][0] is not None]
    headline = None
    if pts:
        change = change_between(pts[-2], pts[-1]) if len(pts) > 1 else {"delta": None, "pct": None}
        headline = {"series_key": series_key(param_key, side), "name": param_name(param_key, lang), "unit": param.unit,
                    "value": pts[-1], "previous": pts[-2] if len(pts) > 1 else None,
                    "delta": change["delta"], "pct": change["pct"]}
    dated = [dates[r.id][0] for r in records if dates[r.id][0] is not None]
    return {"key": organ.key, "name": organ_name(organ.key, lang), "scan_count": len(records),
            "latest_date": dated[-1].isoformat() if dated else None,
            "unverified_count": sum(1 for m in rows if not m.verified), "headline": headline}


def sort_index(summaries: list[dict]) -> list[dict]:
    """Newest latest_date first; organs whose scans are all undated go last."""
    order = list(ORGANS)
    return sorted(summaries, key=lambda s: (s["latest_date"] is None, _neg(s["latest_date"]), order.index(s["key"])))


def _neg(iso: str | None) -> int:
    return -dt.date.fromisoformat(iso).toordinal() if iso else 0
