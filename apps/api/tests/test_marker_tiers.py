import datetime as dt

from sqlmodel import Session, select

from config import settings
from db.models import Biomarker, LabReport, MarkerTier
from importers.backfill_tiers import backfill_tiers
from services.lab_rows import ReviewedRow, TierBand
from services.lab_store import delete_report, save_report
from tests.pdf_factory import text_pdf

BANDS = [TierBand(tier="deficient", max=10, label="дефицит"), TierBand(tier="insufficient", min=10, max=29),
         TierBand(tier="normal", min=30, max=100)]


def _row(**over):
    return ReviewedRow(name="Vitamin D (25-OH)", value=27.6, unit="ng/mL", ref_min=30, ref_max=100, tiers=BANDS, **over)


def test_save_report_persists_tiers_for_mapped_markers_only(session):
    report = save_report(session, test_date=dt.date(2025, 12, 20), lab_name="", source="manual", rows=[
        _row(), ReviewedRow(name="Strange thing", value=1, tiers=BANDS)])
    tiers = session.exec(select(MarkerTier)).all()
    assert {t.marker_key for t in tiers} == {"vitamin_d_25_oh"} and len(tiers) == 3
    assert all(t.report_id == report.id and t.unit == "ng/mL" and t.source == "pdf" for t in tiers)
    delete_report(session, report)
    assert session.exec(select(MarkerTier)).all() == []


def test_api_exposes_system_tiers_age_and_retest(client, engine):
    with Session(engine) as s:
        save_report(s, test_date=dt.date(2024, 1, 1), lab_name="", source="manual", rows=[_row()])
        save_report(s, test_date=dt.date.today() - dt.timedelta(days=10), lab_name="", source="manual", rows=[
            _row(), ReviewedRow(name="Ferritin", value=50, unit="ng/mL")])
    rows = {r["marker_key"]: r for r in client.get("/api/v1/biomarkers").json()}
    vd, fe = rows["vitamin_d_25_oh"], rows["ferritin"]
    assert vd["system"] == "vitamins" and vd["retest_days"] == 90 and vd["age_days"] == 10
    assert [t["tier"] for t in vd["tiers"]] == ["deficient", "insufficient", "normal"]  # newest report's tiers, once
    assert vd["tiers"][1] == {"tier": "insufficient", "min": 10.0, "max": 29.0, "label": "", "unit": "ng/mL", "report_id": vd["tiers"][1]["report_id"]}
    assert vd["tiers"][1]["report_id"] is not None
    assert fe["tiers"] == []
    h = client.get("/api/v1/biomarkers/vitamin_d_25_oh/history").json()
    assert h["system"] == "vitamins" and h["retest_days"] == 90 and len(h["tiers"]) == 3


def test_unmapped_marker_is_other_without_retest(client, engine):
    with Session(engine) as s:
        save_report(s, test_date=dt.date(2025, 1, 1), lab_name="", source="manual", rows=[ReviewedRow(name="Mucus", value=1)])
    row = client.get("/api/v1/biomarkers").json()[0]
    assert row["system"] == "other" and row["retest_days"] is None and row["tiers"] == []


def test_backfill_fills_missing_tiers_from_the_stored_pdf_and_is_rerunnable(session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    lines = ("Results Reference Unit", "Date 2025-12-20", "Total Vitamin D - 25 OH 27,6",
             "deficient state: < 10 ng/ml", "insufficient: 10 - < 29 ng/ml", "normal state: 30 - 100 ng/ml")
    content = text_pdf(*lines)
    (tmp_path / "pdf").mkdir()
    (tmp_path / "pdf" / "abc.pdf").write_bytes(content)
    report = LabReport(test_date=dt.date(2025, 12, 20), source="pdf", file_hash="abc")
    session.add(report)
    session.flush()
    session.add(Biomarker(report_id=report.id, marker_key="vitamin_d_25_oh", display_name="Vitamin D", value=27.6, unit="ng/mL"))
    session.commit()
    assert backfill_tiers(session) == 1
    tiers = session.exec(select(MarkerTier)).all()
    assert [t.tier for t in sorted(tiers, key=lambda t: t.min_value or -1)] == ["deficient", "insufficient", "normal"]
    assert backfill_tiers(session) == 0 and len(session.exec(select(MarkerTier)).all()) == 3
