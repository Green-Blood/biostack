import datetime as dt

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel

from db.models import Biomarker, LabReport, MedicalRecord


def test_all_prd_and_extra_tables_exist():
    names = set(SQLModel.metadata.tables)
    assert {
        "labreport", "biomarker", "imagingstudy", "dailymetric", "supplementlog",
        "environmentallog", "healthjournal", "cnstest", "correlationcache",
        "clinic", "medicalrecord", "medication", "recordmedication",
        "markeralias", "datereview",
    } <= names


def test_biomarker_source_external_id_is_unique(session):
    rep = LabReport(test_date=dt.date(2022, 1, 15), lab_name="x")
    session.add(rep)
    session.commit()
    for _ in range(2):
        session.add(Biomarker(report_id=rep.id, marker_key="ferritin", display_name="Ferritin",
                              raw_name="Ferritin", value=28.0, unit="ng/mL",
                              source="notion", external_id="p1#0"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_medical_record_roundtrip_keeps_cyrillic(session):
    session.add(MedicalRecord(title="Визит к ортопеду", record_type="visit",
                              record_date=dt.date(2026, 10, 15), source="notion", external_id="a"))
    session.commit()
    got = session.query(MedicalRecord).one()
    assert got.title == "Визит к ортопеду"
    assert got.date_suspect is False
