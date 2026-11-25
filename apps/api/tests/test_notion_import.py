import datetime as dt
import json
from pathlib import Path

from sqlmodel import select

from db.models import (Biomarker, Clinic, DateReview, MarkerAlias, MedicalRecord, Medication,
                       RecordMedication)
from importers.notion_import import import_snapshot

FIX = Path(__file__).parent / "fixtures" / "mini_snapshot.json"


def counts(session):
    return {m.__name__: len(session.exec(select(m)).all())
            for m in (MedicalRecord, Biomarker, Medication, Clinic)}


def test_import_creates_expected_rows(session):
    rep = import_snapshot(FIX, session)
    assert (rep.records, rep.clinics, rep.medications) == (2, 1, 1)
    assert rep.biomarkers == 4  # 3 table rows + 1 analysis
    r1 = session.exec(select(MedicalRecord).where(MedicalRecord.external_id == "r1")).one()
    assert r1.record_type == "visit" and r1.clinic_id is not None
    assert len(session.exec(select(RecordMedication)).all()) == 1


def test_out_of_range_is_computed_not_copied(session):
    import_snapshot(FIX, session)
    fe = session.exec(select(Biomarker).where(Biomarker.marker_key == "ferritin")).one()
    assert fe.is_out_of_range is True and fe.unit == "ng/mL" and fe.ref_min == 30.0
    vd = session.exec(select(Biomarker).where(Biomarker.marker_key == "vitamin_d_25_oh")).one()
    assert vd.value == 24.0 and vd.is_out_of_range is True


def test_unmapped_marker_reported_and_kept(session):
    rep = import_snapshot(FIX, session)
    assert rep.unmapped_markers == ["Mystery Marker"]
    b = session.exec(select(Biomarker).where(Biomarker.raw_name == "Mystery Marker")).one()
    assert b.marker_key.startswith("unmapped:")


def test_suspect_dates_flagged(session):
    rep = import_snapshot(FIX, session)
    assert rep.suspect_dates == ["Blood panel"]
    assert session.exec(select(MedicalRecord).where(MedicalRecord.external_id == "r2")).one().date_suspect


def test_import_is_idempotent(session):
    import_snapshot(FIX, session)
    first = counts(session)
    import_snapshot(FIX, session)
    assert counts(session) == first


def test_reimport_updates_changed_value_without_duplicates(session, tmp_path):
    import_snapshot(FIX, session)
    snap = json.loads(FIX.read_text(encoding="utf-8"))
    snap["records"][1]["body_markdown"] = snap["records"][1]["body_markdown"].replace("28 ng/mL", "35 ng/mL")
    p = tmp_path / "s.json"
    p.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    before = counts(session)
    import_snapshot(p, session)
    assert counts(session) == before
    fe = session.exec(select(Biomarker).where(Biomarker.marker_key == "ferritin")).one()
    assert fe.value == 35.0 and fe.is_out_of_range is False


def test_reimport_removes_row_deleted_in_notion(session, tmp_path):
    import_snapshot(FIX, session)
    snap = json.loads(FIX.read_text(encoding="utf-8"))
    snap["records"][1]["body_markdown"] = "\n".join(snap["records"][1]["body_markdown"].splitlines()[:4]) + "\n"
    p = tmp_path / "s.json"
    p.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    import_snapshot(p, session)
    assert session.exec(select(Biomarker).where(Biomarker.raw_name == "Mystery Marker")).first() is None


def test_review_decisions_survive_reimport(session):
    import_snapshot(FIX, session)
    r2 = session.exec(select(MedicalRecord).where(MedicalRecord.external_id == "r2")).one()
    session.add(DateReview(record_id=r2.id, confirmed_date=dt.date(2022, 1, 15)))
    session.add(MarkerAlias(raw_name="Mystery Marker", marker_key="mystery", display_name="Mystery"))
    session.commit()
    import_snapshot(FIX, session)
    assert session.get(DateReview, r2.id).confirmed_date == dt.date(2022, 1, 15)
    assert session.exec(select(MarkerAlias)).one().marker_key == "mystery"
    # alias now resolves the previously unmapped marker on re-import
    assert session.exec(select(Biomarker).where(Biomarker.marker_key == "mystery")).one()


def test_html_markup_is_cleaned_from_text(session):
    import_snapshot(FIX, session)
    r1 = session.exec(select(MedicalRecord).where(MedicalRecord.external_id == "r1")).one()
    assert r1.details == "жалобы\nнет"


def test_blank_named_and_valueless_entries_are_skipped(session):
    import_snapshot(FIX, session)
    assert session.exec(select(Medication).where(Medication.name == "")).first() is None
    assert session.exec(select(Biomarker).where(Biomarker.raw_name == "")).first() is None
    # valueless Analysis Tracker rows are imaging pointers, not biomarkers
    assert session.exec(select(Biomarker).where(Biomarker.raw_name == "УЗИ щитовидной")).first() is None


def test_removing_lab_table_in_notion_removes_its_results(session, tmp_path):
    from db.models import LabReport
    import_snapshot(FIX, session)
    snap = json.loads(FIX.read_text(encoding="utf-8"))
    snap["records"][1]["body_markdown"] = "just prose now"
    p = tmp_path / "s.json"
    p.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    import_snapshot(p, session)
    assert session.exec(select(Biomarker).where(Biomarker.raw_name == "Ferritin")).first() is None
    r2 = session.exec(select(MedicalRecord).where(MedicalRecord.external_id == "r2")).one()
    assert session.exec(select(LabReport).where(LabReport.record_id == r2.id)).first() is None


def test_undated_analysis_is_skipped_and_reported_not_dated_today(session):
    rep = import_snapshot(FIX, session)
    assert rep.undated_analyses == ["Vitamin D"]
    vd = session.exec(select(Biomarker).where(Biomarker.marker_key == "vitamin_d_25_oh")).all()
    assert [b.external_id for b in vd] == ["analysis:a1"]
