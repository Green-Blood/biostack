import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from db.database import get_session
from db.models import DEMO_SOURCE, MedicalRecord, Medication
from services import app_settings, clock
from services.i18n import Lang, get_lang, msg
from services.markers import canonical_unit, catalog_markers, marker_display_name, marker_retest_days, marker_system
from services.queries import biomarker_rows as _rows, effective_dates
from services.tiers import latest_tiers, tiers_for_unit
from services.trends import Point, compute_deltas, pct_of_range

router = APIRouter(tags=["biomarkers"])


@router.get("/biomarkers")
def list_biomarkers(session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    groups: dict[str, list] = {}
    for bm, date, _suspect in _rows(session):
        groups.setdefault(bm.marker_key, []).append((bm, date))
    out = []
    tiers = latest_tiers(session)
    today = clock.today(app_settings.configured_zone(session))
    for key, items in groups.items():
        numeric = [(b, d) for b, d in items if b.value is not None]
        latest = numeric[-1] if numeric else None
        text = next((b.result_text for b, _ in reversed(items) if b.result_text), None)
        out.append({
            "marker_key": key, "display_name": marker_display_name(key, items[-1][0].display_name, lang),
            "unit": latest[0].unit if latest else "", "count": len(numeric),
            "latest_value": latest[0].value if latest else None,
            "latest_date": (latest[1] if latest else items[-1][1]).isoformat(),
            "ref_min": latest[0].ref_min if latest else None,
            "ref_max": latest[0].ref_max if latest else None,
            "needs_profile": latest[0].needs_profile if latest and latest[0].ref_min is None and latest[0].ref_max is None else None,
            "is_demo": bool(latest and latest[0].source == DEMO_SOURCE), "latest_text": text, "out_of_range_latest": bool(latest and latest[0].is_out_of_range),
            "spark": [b.value for b, _ in numeric][-12:],
            "system": marker_system(key),
            "tiers": tiers_for_unit(tiers.get(key, []), latest[0].unit) if latest else [],
            "age_days": max((today - (latest[1] if latest else items[-1][1])).days, 0),
            "retest_days": marker_retest_days(key),
        })
    out.sort(key=lambda r: (r["marker_key"].startswith("unmapped:"), r["display_name"].lower()))
    return out


@router.get("/labs/marker-catalog")
def marker_catalog(lang: Lang = Depends(get_lang)):
    return catalog_markers(lang)


@router.get("/biomarkers/compare")
def compare(keys: str, dates: str, session: Session = Depends(get_session)):
    wanted = [dt.date.fromisoformat(d) for d in dates.split(",") if d]
    result = {}
    for key in [k for k in keys.split(",") if k]:
        pts = [(b, d) for b, d, _ in _rows(session, key) if b.value is not None]
        col = []
        for want in wanted:
            if not pts:
                col.append({"date": want.isoformat(), "value": None, "unit": "", "pct_of_range": None})
                continue
            b, d = min(pts, key=lambda t: abs((t[1] - want).days))
            col.append({"date": d.isoformat(), "value": b.value, "unit": b.unit,
                        "pct_of_range": pct_of_range(b.value, b.ref_min, b.ref_max)})
        result[key] = col
    return result


@router.get("/biomarkers/{marker_key}/history")
def history(marker_key: str, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)):
    rows = _rows(session, marker_key)
    if not rows:
        raise HTTPException(404, msg(lang, "http.marker_unknown"))
    numeric = [(b, d, s) for b, d, s in rows if b.value is not None]
    points = [{"date": d.isoformat(), "value": b.value, "ref_min": b.ref_min, "ref_max": b.ref_max,
               "out_of_range": b.is_out_of_range, "date_suspect": s, "unit": b.unit,
               "is_demo": b.source == DEMO_SOURCE} for b, d, s in numeric]
    deltas = compute_deltas([Point(d.isoformat(), b.value, b.ref_min, b.ref_max) for b, d, _ in numeric])
    # a missing unit next to a real one is also a mismatch: we cannot know they agree
    units = {canonical_unit(marker_key, b.unit) for b, _, _ in numeric}
    ranges = {(b.ref_min, b.ref_max) for b, _, _ in numeric}
    return {
        "marker_key": marker_key, "display_name": marker_display_name(marker_key, rows[-1][0].display_name, lang),
        "unit": numeric[-1][0].unit if numeric else "", "points": points,
        "deltas": [d.__dict__ for d in deltas], "unit_mismatch": len(units) > 1, "range_mismatch": len(ranges) > 1,
        "enough_data": len(numeric) >= 2,
        "system": marker_system(marker_key), "tiers": latest_tiers(session).get(marker_key, []),
        "retest_days": marker_retest_days(marker_key),
        "text_results": [{"date": d.isoformat(), "text": b.result_text} for b, d, _ in rows if b.result_text],
    }


@router.get("/context")
def context(session: Session = Depends(get_session), from_: dt.date | None = Query(None, alias="from"),
            to: dt.date | None = None):
    eff = effective_dates(session)
    lo, hi = from_ or dt.date.min, to or dt.date.max
    meds = []
    for m in session.exec(select(Medication)):
        start, end = m.start_date, m.end_date or m.start_date
        if start and start <= hi and (end or start) >= lo:
            meds.append({"name": m.name, "dosage": m.dosage, "start": start.isoformat(),
                         "end": m.end_date.isoformat() if m.end_date else None})
    recs = []
    for r in session.exec(select(MedicalRecord)):
        d = eff[r.id][0]
        if d and lo <= d <= hi:
            recs.append({"id": r.id, "date": d.isoformat(), "title": r.title, "record_type": r.record_type,
                         "is_demo": r.source == DEMO_SOURCE})
    recs.sort(key=lambda r: r["date"])
    return {"medications": meds, "records": recs}
