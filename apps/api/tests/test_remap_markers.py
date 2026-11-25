import datetime as dt

from sqlmodel import select

from db.models import Biomarker, LabReport
from services.lab_store import remap_unmapped_biomarkers


def _row(session, raw_name, key="unmapped:x", unit="", source="pdf"):
    report = LabReport(test_date=dt.date(2025, 1, 1), source=source)
    session.add(report)
    session.flush()
    session.add(Biomarker(report_id=report.id, marker_key=key, display_name=raw_name, raw_name=raw_name,
                          value=1.0, unit=unit, is_out_of_range=False, source=source))
    session.commit()


def test_rows_whose_name_is_now_in_the_catalog_are_mapped(session):
    _row(session, "Ферритин")
    _row(session, "A name nobody has heard of")
    assert remap_unmapped_biomarkers(session) == 1
    rows = {b.raw_name: b for b in session.exec(select(Biomarker))}
    assert rows["Ферритин"].marker_key == "ferritin" and rows["Ферритин"].display_name == "Ferritin"
    assert rows["A name nobody has heard of"].marker_key == "unmapped:x"


def test_already_mapped_rows_are_not_touched(session):
    _row(session, "Ферритин", key="custom_key")
    assert remap_unmapped_biomarkers(session) == 0
    assert session.exec(select(Biomarker)).one().marker_key == "custom_key"


def test_a_pdf_result_keeps_the_date_printed_on_the_report_not_its_records_date(client, session):
    from db.models import MedicalRecord

    record = MedicalRecord(title="Visit", record_date=dt.date(2025, 12, 22), source="notion", external_id="p")
    session.add(record)
    session.flush()
    report = LabReport(test_date=dt.date(2025, 12, 25), source="pdf", record_id=record.id)
    session.add(report)
    session.flush()
    session.add(Biomarker(report_id=report.id, marker_key="iodine_serum", display_name="Iodine (serum)", raw_name="x",
                          value=95.5, unit="", is_out_of_range=True, source="pdf"))
    session.commit()
    points = client.get("/api/v1/biomarkers/iodine_serum/history").json()["points"]
    assert [p["date"] for p in points] == ["2025-12-25"]
