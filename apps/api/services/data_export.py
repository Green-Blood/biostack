import csv
import datetime as dt
import io
import json
import re
import tempfile
import zipfile
from pathlib import Path

from fastapi.encoders import jsonable_encoder
from sqlmodel import Session, SQLModel, select

from config import settings
from db.models import (
    Biomarker, BodyMeasurement, Diagnosis, ImagingStudy, LabReport, MedicalRecord, Medication,
    Profile, RecordAttachment, RecordMedication, RecordNote,
)


def export_all_tables(session: Session) -> dict[str, list[dict]]:
    """Every table's rows keyed by table name; the owner's complete data as plain JSON."""
    return {
        table.name: [jsonable_encoder(dict(row._mapping)) for row in session.execute(select(table))]
        for table in SQLModel.metadata.sorted_tables
    }


MANIFEST = "data/files-manifest.json"
TABLES_JSON = "data/all-tables.json"


_README = """# BioStack export

This is one person's private health data exported from their own BioStack database
(exported {today}). It is meant to be read by a person or handed to an AI assistant.
Reference ranges are exactly as printed by the lab; "out of range" was computed from them.
Nothing here is a diagnosis. Values older than the retest interval are history, not the present state.

## What is inside

| Path | What it is |
|------|-----------|
| `README.md` | this guide |
| `profile.md` | age, sex, height, latest weight and BMI |
| `records.md` | every visit, hospital stay, procedure: diagnoses, treatments, notes, files, in date order |
| `biomarkers.csv` | every lab result, one row each: date, marker, value, unit, printed range, flag, lab, source file |
| `courses.csv` | medicines and supplements with dose, route, frequency and dates |
| `body.csv` | weight and waist measurements |
| `imaging.csv` | imaging studies and their reports |
| `data/all-tables.json` | the complete database, every table, for programs |
| `files/` | the original PDFs and photos, named `<record id>-<original name>`; `files/labs/` holds lab report PDFs |
| `imaging/` | scan key frames (PNG) and, when the export was asked to include them, the DICOM archives |
| `data/files-manifest.json` | where each file belongs inside the data folder, so the ZIP can be imported back |

## Suggested prompt

"Here is my health history. Read `profile.md`, `biomarkers.csv`, `courses.csv` and `records.md`.
Summarise what is out of range and how each marker changed over time, point out results that are
too old to rely on, and list questions I should ask my doctor. Do not diagnose."

Counts: {counts}
"""


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w.\- ()]+", "_", name, flags=re.UNICODE).strip() or "file"


def _csv(rows: list[list], header: list[str]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue()


def _age(birth: dt.date, today: dt.date) -> int:
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def _profile_md(session: Session, today: dt.date) -> str:
    profile = session.get(Profile, 1)
    weights = session.exec(select(BodyMeasurement).where(BodyMeasurement.kind == "weight")
                           .order_by(BodyMeasurement.measured_on.desc())).first()
    lines = ["# Profile", ""]
    if profile is None or not (profile.birth_date or profile.sex or profile.height_cm):
        return "\n".join(lines + ["Not filled in."]) + "\n"
    if profile.birth_date:
        lines.append(f"- Age: {_age(profile.birth_date, today)} (born {profile.birth_date})")
    if profile.sex:
        lines.append(f"- Sex: {profile.sex}")
    if profile.height_cm:
        lines.append(f"- Height: {profile.height_cm:g} cm")
    if weights:
        lines.append(f"- Latest weight: {weights.value:g} kg on {weights.measured_on}")
        if profile.height_cm:
            lines.append(f"- BMI: {weights.value / (profile.height_cm / 100) ** 2:.1f} (rough screening only)")
    return "\n".join(lines) + "\n"


def _records_md(session: Session, attachment_names: dict[int, list[str]]) -> str:
    records = session.exec(select(MedicalRecord)).all()
    records.sort(key=lambda r: (r.record_date or dt.date.min, r.id or 0))
    meds = {m.id: m for m in session.exec(select(Medication)).all()}
    links: dict[int, list[int]] = {}
    for link in session.exec(select(RecordMedication)).all():
        links.setdefault(link.record_id, []).append(link.medication_id)
    diagnoses: dict[int, list[Diagnosis]] = {}
    for d in session.exec(select(Diagnosis)).all():
        diagnoses.setdefault(d.record_id, []).append(d)
    notes: dict[int, list[RecordNote]] = {}
    for n in session.exec(select(RecordNote).order_by(RecordNote.note_date)).all():
        notes.setdefault(n.record_id, []).append(n)

    out = ["# Medical records", ""]
    if not records:
        return "\n".join(out + ["None."]) + "\n"
    for r in records:
        span = f"{r.record_date or 'no date'}" + (f" to {r.end_date}" if r.end_date else "")
        out += [f"## {span} — {r.title} ({r.record_type})", ""]
        for label, value in (("Status", r.status), ("Department", r.department), ("Doctor", r.doctor_name), ("Reason", r.reason)):
            if value:
                out.append(f"- {label}: {value}")
        if r.details:
            out += ["", "Details:", r.details.strip()]
        if r.doctors_note:
            out += ["", "Doctor's note:", r.doctors_note.strip()]
        if r.body_markdown:
            out += ["", r.body_markdown.strip()]
        if diagnoses.get(r.id):
            out += ["", "Diagnoses:"]
            out += [f"- {d.name}" + (f" [{d.icd10}]" if d.icd10 else "") + f" — {d.status}" + (f". {d.note}" if d.note else "")
                    for d in diagnoses[r.id]]
        treatments = [meds[i] for i in links.get(r.id, []) if i in meds]
        if treatments:
            out += ["", "Treatment:"]
            for m in treatments:
                bits = [b for b in (m.dosage, m.route, m.frequency) if b]
                period = f"{m.start_date or '?'} to {m.end_date or '?'}"
                out.append(f"- {m.name}" + (f" ({', '.join(bits)})" if bits else "") + f", {period}")
        if notes.get(r.id):
            out += ["", "Notes and questions:"]
            out += [f"- {n.note_date}{' [question' + (', answered' if n.done else ', open') + ']' if n.kind == 'question' else ''}: {n.text}"
                    for n in notes[r.id]]
        if attachment_names.get(r.id):
            out += ["", "Files:"] + [f"- files/{name}" for name in attachment_names[r.id]]
        out.append("")
    return "\n".join(out)


def _unique(name: str, taken: set[str]) -> str:
    candidate, stem, suffix, n = name, Path(name).stem, Path(name).suffix, 1
    while candidate in taken:
        n += 1
        candidate = f"{stem} ({n}){suffix}"
    taken.add(candidate)
    return candidate


def record_texts(session: Session, reports: dict[int, LabReport], report_files: dict[int, str],
                attachment_names: dict[int, list[str]], today: dt.date) -> tuple[dict[str, str], dict[str, int]]:
    """The readable text files of the archive, by name, plus row counts. The AI chat is fed the very same text."""
    bio_rows = []
    for b in session.exec(select(Biomarker)).all():
        rep = reports.get(b.report_id)
        value = b.value if b.value is not None else (f"{b.comparator or ''}{b.result_text or ''}")
        bio_rows.append([rep.test_date if rep else "", b.marker_key, b.display_name, value, b.unit, b.ref_min if b.ref_min is not None else "",
                         b.ref_max if b.ref_max is not None else "", "out of range" if b.is_out_of_range else "",
                         rep.lab_name if rep else "", report_files.get(b.report_id, "")])
    bio_rows.sort(key=lambda r: (str(r[1]), str(r[0])))

    meds = session.exec(select(Medication).order_by(Medication.start_date)).all()
    med_rows = [[m.name, m.dosage, m.route or "", m.frequency or "", m.start_date or "", m.end_date or "", m.target_marker_key or "", m.notes] for m in meds]
    body_rows = [[m.measured_on, m.kind, m.value, m.source] for m in session.exec(select(BodyMeasurement).order_by(BodyMeasurement.measured_on)).all()]
    imaging_rows = [[s.study_date, s.study_type, s.body_part, s.series_description, s.slice_count, s.summary_text]
                    for s in session.exec(select(ImagingStudy).order_by(ImagingStudy.study_date)).all()]

    texts = {
        "profile.md": _profile_md(session, today),
        "records.md": _records_md(session, attachment_names),
        "biomarkers.csv": _csv(bio_rows, ["date", "marker_key", "name", "value", "unit", "ref_min", "ref_max", "flag", "lab", "source_file"]),
        "courses.csv": _csv(med_rows, ["name", "dose", "route", "frequency", "start", "end", "target_marker", "notes"]),
        "body.csv": _csv(body_rows, ["date", "kind", "value", "source"]),
        "imaging.csv": _csv(imaging_rows, ["date", "type", "body_part", "series", "slices", "report"]),
    }
    return texts, {"lab results": len(bio_rows), "medicines/courses": len(med_rows)}


def build_archive(session: Session, data_dir: Path | None = None, today: dt.date | None = None,
                  include_dicom: bool = False) -> Path:
    """Write the whole archive to a temporary .zip file and return its path (the caller deletes it).

    DICOM archives are large, so they go in only when `include_dicom` is set; key frames always do."""
    data_dir = data_dir or settings.data_dir
    today = today or dt.date.today()
    tables = export_all_tables(session)
    reports = {r.id: r for r in session.exec(select(LabReport)).all()}
    taken: set[str] = set()
    attachment_names: dict[int, list[str]] = {}
    file_jobs: list[tuple[Path, str]] = []

    for att in session.exec(select(RecordAttachment).order_by(RecordAttachment.id)).all():
        source = data_dir / att.stored_path
        if not source.is_file():
            continue
        arc = _unique(f"{att.record_id}-{_safe_name(att.filename)}", taken)
        attachment_names.setdefault(att.record_id, []).append(arc)
        file_jobs.append((source, f"files/{arc}"))

    report_files: dict[int, str] = {}
    for rep in reports.values():
        if rep.pdf_path and (data_dir / rep.pdf_path).is_file():
            arc = _unique(f"{rep.test_date}-{_safe_name(rep.lab_name)}-{rep.id}{Path(rep.pdf_path).suffix}", set())
            report_files[rep.id] = f"files/labs/{arc}"
            file_jobs.append((data_dir / rep.pdf_path, report_files[rep.id]))

    for study in session.exec(select(ImagingStudy).order_by(ImagingStudy.id)).all():
        paths = list(study.keyframe_paths or []) + ([study.zip_path] if include_dicom and study.zip_path else [])
        for rel in paths:
            if (data_dir / rel).is_file():
                file_jobs.append((data_dir / rel, f"imaging/{rel.removeprefix('imaging/')}"))

    texts, extra = record_texts(session, reports, report_files, attachment_names, today)
    counts = ", ".join(f"{n} {label}" for n, label in (
        (len(tables.get("medicalrecord", [])), "records"), (len(reports), "lab reports"), (extra["lab results"], "lab results"),
        (extra["medicines/courses"], "medicines/courses"), (len(file_jobs), "original files")))
    handle = tempfile.NamedTemporaryFile(prefix="biostack-export-", suffix=".zip", delete=False)
    handle.close()
    with zipfile.ZipFile(handle.name, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.md", _README.format(today=today, counts=counts))
        for name, text in texts.items():
            z.writestr(name, text)
        z.writestr("data/all-tables.json", json.dumps(tables, indent=2, ensure_ascii=False))
        manifest = {arc: source.relative_to(data_dir).as_posix() for source, arc in file_jobs}
        z.writestr(MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False))
        for source, arc in file_jobs:
            z.write(source, arc)
    return Path(handle.name)
