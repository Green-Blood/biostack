"""Idempotent importer: Notion snapshot (JSON) -> BioStack database. Makes no AI calls."""
import datetime as dt
import html
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlmodel import Session, select

from db.models import (Biomarker, Clinic, LabReport, MedicalRecord, Medication, RecordMedication)
from services.lab_rows import is_out_of_range, slug
from services.lab_table_parser import parse_markdown_lab_table, parse_reference, parse_result
from services.markers import canonical_unit, normalize_marker

SOURCE = "notion"
SUSPECT_DAYS = 365

_IMAGING = ("ultrasound", "узи", "мскт", "мрт", "ct ", "mri", "x-ray", "рентген")
_VISIT = ("visit", "визит", "уролог", "гастро", "эндокрин", "ортопед", "невролог", "лор",
          "проктолог", "физиотерапевт", "neurolog", "urolog", "gastro", "endocrin", "косметолог",
          "лазер")


@dataclass
class ImportReport:
    records: int = 0
    biomarkers: int = 0
    medications: int = 0
    clinics: int = 0
    unmapped_markers: list[str] = field(default_factory=list)
    suspect_dates: list[str] = field(default_factory=list)
    undated_analyses: list[str] = field(default_factory=list)


def _clean(text: str | None) -> str:
    """Notion returns HTML-ish markup in text properties; reduce it to plain text."""
    t = re.sub(r"<br\s*/?>|</p>|</div>", "\n", text or "", flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return "\n".join(line.strip() for line in t.splitlines()).strip()


def _date(s: str | None) -> dt.date | None:
    return dt.date.fromisoformat(s[:10]) if s else None


def _classify(title: str, has_labs: bool) -> str:
    low = title.lower()
    if has_labs:
        return "lab"
    if any(w in low for w in _IMAGING):
        return "imaging"
    if any(w in low for w in _VISIT):
        return "visit"
    return "other"


def _upsert(session: Session, model, external_id: str, **fields):
    obj = session.exec(select(model).where(model.source == SOURCE,
                                           model.external_id == external_id)).first()
    if obj is None:
        obj = model(source=SOURCE, external_id=external_id, **fields)
        session.add(obj)
    else:
        for k, v in fields.items():
            setattr(obj, k, v)
    session.flush()
    return obj


def _upsert_biomarker(session, report, ext_id, raw_name, result: str, reference: str, rep, unit_hint: str = ""):
    parsed = parse_result(result)
    lo, hi = parse_reference(reference)
    match = normalize_marker(raw_name, session)
    if match is None:
        key, display = f"unmapped:{slug(raw_name)}", raw_name
        if raw_name not in rep.unmapped_markers:
            rep.unmapped_markers.append(raw_name)
    else:
        key, display = match.marker_key, match.display_name
    _upsert(session, Biomarker, ext_id, report_id=report.id, marker_key=key, display_name=display,
            raw_name=raw_name, value=parsed.value, result_text=parsed.result_text,
            comparator=parsed.comparator, unit=canonical_unit(key, parsed.unit or unit_hint),
            ref_min=lo, ref_max=hi, is_out_of_range=is_out_of_range(parsed.value, lo, hi))
    rep.biomarkers += 1


def _link(session, record_id: int, medication_id: int) -> None:
    if session.get(RecordMedication, (record_id, medication_id)) is None:
        session.add(RecordMedication(record_id=record_id, medication_id=medication_id))


def import_snapshot(path: Path, session: Session) -> ImportReport:
    snap = json.loads(Path(path).read_text(encoding="utf-8"))
    rep = ImportReport()

    clinics = {}
    for c in snap.get("clinics", []):
        if not _clean(c["name"]):
            continue
        clinics[c["id"]] = _upsert(session, Clinic, c["id"], name=_clean(c["name"]))
        rep.clinics += 1

    meds_by_name: dict[str, Medication] = {}
    for m in snap.get("medications", []):
        if not _clean(m["name"]):
            continue
        med = _upsert(session, Medication, m["id"], name=_clean(m["name"]), dosage=_clean(m.get("dosage")),
                      start_date=_date(m.get("start")), end_date=_date(m.get("end")),
                      notes=_clean(m.get("notes")))
        meds_by_name[_clean(m["name"])] = med
        rep.medications += 1

    records_by_id: dict[str, MedicalRecord] = {}
    for r in snap.get("records", []):
        title = _clean(r["title"]) or "(untitled)"
        rows = parse_markdown_lab_table(r.get("body_markdown") or "")
        date = _date(r.get("date"))
        edited = _date(r.get("last_edited_time"))
        suspect = date is None or (edited is not None and abs((edited - date).days) > SUSPECT_DAYS)
        clinic = clinics.get((r.get("clinic_ids") or [None])[0])
        rec = _upsert(session, MedicalRecord, r["id"], record_date=date, date_suspect=suspect,
                      title=title, record_type=_classify(title, bool(rows)),
                      clinic_id=clinic.id if clinic else None, details=_clean(r.get("details")),
                      doctors_note=_clean(r.get("doctors_note")),
                      body_markdown=r.get("body_markdown") or "")
        records_by_id[r["id"]] = rec
        rep.records += 1
        if suspect:
            rep.suspect_dates.append(title)

        for name in filter(None, map(_clean, r.get("medications") or [])):
            med = meds_by_name.get(name)
            if med is None:
                med = _upsert(session, Medication, f"name:{name}", name=name)
                meds_by_name[name] = med
                rep.medications += 1
            _link(session, rec.id, med.id)

        if not rows:
            # the lab table was removed in Notion: drop the results imported from it
            old = session.exec(select(LabReport).where(LabReport.source == SOURCE,
                                                       LabReport.external_id == r["id"])).first()
            if old is not None:
                for b in session.exec(select(Biomarker).where(Biomarker.report_id == old.id)):
                    session.delete(b)
                session.delete(old)
        if rows:
            test_date = date or _date(r.get("created_time")) or dt.date.today()
            report = _upsert(session, LabReport, r["id"], test_date=test_date,
                             lab_name=clinic.name if clinic else "", record_id=rec.id)
            keep = set()
            for i, row in enumerate(rows):
                ext = f"{r['id']}#{i}"
                keep.add(ext)
                _upsert_biomarker(session, report, ext, row.name, row.result, row.reference, rep, row.unit)
            for stale in session.exec(select(Biomarker).where(
                    Biomarker.report_id == report.id, Biomarker.source == SOURCE)):
                if stale.external_id not in keep:
                    session.delete(stale)

    for m in snap.get("medications", []):
        name = _clean(m["name"])
        for rid in m.get("record_ids") or []:
            if rid in records_by_id and name in meds_by_name:
                _link(session, records_by_id[rid].id, meds_by_name[name].id)

    for a in snap.get("analyses", []):
        # Analysis Tracker rows without a numeric value are imaging pointers, not biomarkers.
        if a.get("value") is None or not _clean(a["name"]):
            continue
        if not a.get("date"):
            # never guess "today" for a result: it would move on every re-import
            rep.undated_analyses.append(_clean(a["name"]))
            continue
        ids = [i for i in a.get("record_ids") or [] if i in records_by_id]
        d = _date(a["date"])
        report = _upsert(session, LabReport, f"analysis:{a['id']}", test_date=d, lab_name="",
                         record_id=records_by_id[ids[0]].id if ids else None)
        value = a.get("value")
        _upsert_biomarker(session, report, f"analysis:{a['id']}", _clean(a["name"]),
                          str(value), a.get("reference_range") or "", rep)

    session.commit()
    return rep


if __name__ == "__main__":
    from sqlmodel import SQLModel

    from db.database import engine

    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        report = import_snapshot(Path(sys.argv[1]), s)
    print(report)
