import datetime as dt

from sqlmodel import Session

from db.models import (Biomarker, Clinic, LabReport, MedicalRecord, Medication, RecordMedication)


def seed(engine):
    with Session(engine) as s:
        clinic = Clinic(name="Akfa")
        s.add(clinic)
        s.flush()
        rec = MedicalRecord(title="Визит к урологу", record_type="visit", record_date=dt.date(2023, 5, 1),
                            clinic_id=clinic.id, details="боль", source="t", external_id="r1")
        sus = MedicalRecord(title="Old panel", record_type="lab", record_date=dt.date(2022, 1, 15),
                            date_suspect=True, source="t", external_id="r2")
        s.add_all([rec, sus])
        s.flush()
        med = Medication(name="Креон", start_date=dt.date(2023, 4, 1), end_date=dt.date(2023, 6, 1))
        s.add(med)
        s.flush()
        s.add(RecordMedication(record_id=rec.id, medication_id=med.id))
        for i, (d, v, unit) in enumerate([("2022-01-15", 18, "ng/mL"), ("2023-05-01", 24, "ng/mL"),
                                           ("2024-03-01", 31, "ng/mL")]):
            rep = LabReport(test_date=dt.date.fromisoformat(d), record_id=sus.id if i == 0 else None)
            s.add(rep)
            s.flush()
            s.add(Biomarker(report_id=rep.id, marker_key="vitamin_d_25_oh", display_name="Vitamin D",
                            raw_name="Vitamin D", value=v, unit=unit, ref_min=30, ref_max=100,
                            is_out_of_range=v < 30))
        rep = LabReport(test_date=dt.date(2024, 3, 1))
        s.add(rep)
        s.flush()
        s.add_all([
            Biomarker(report_id=rep.id, marker_key="ferritin", display_name="Ferritin", raw_name="Ferritin",
                      value=50, unit="ng/mL", ref_min=30, ref_max=400),
            Biomarker(report_id=rep.id, marker_key="unmapped:mucus", display_name="Mucus", raw_name="Mucus",
                      result_text="+"),
        ])
        s.commit()


def test_records_timeline(client, engine):
    seed(engine)
    rows = client.get("/api/v1/records").json()
    assert [r["title"] for r in rows] == ["Визит к урологу", "Old panel"]  # newest first
    first = rows[0]
    assert first["clinic"] == "Akfa" and first["medications"] == ["Креон"] and first["has_labs"] is False
    assert client.get("/api/v1/records", params={"type": "lab"}).json()[0]["title"] == "Old panel"
    assert len(client.get("/api/v1/records", params={"q": "УРОЛОГУ"}).json()) == 1  # case-insensitive RU
    assert len(client.get("/api/v1/records", params={"from": "2023-01-01"}).json()) == 1


def test_marker_history_three_points(client, engine):
    seed(engine)
    h = client.get("/api/v1/biomarkers/vitamin_d_25_oh/history").json()
    assert [p["value"] for p in h["points"]] == [18, 24, 31]
    assert h["enough_data"] is True and h["unit_mismatch"] is False and h["unit"] == "ng/mL"
    assert [d["abs"] for d in h["deltas"]] == [6, 7]
    assert h["points"][0]["date_suspect"] is True  # linked record has an unverified date


def test_single_point_not_enough_data(client, engine):
    seed(engine)
    h = client.get("/api/v1/biomarkers/ferritin/history").json()
    assert h["enough_data"] is False and h["deltas"] == []


def test_unknown_marker_404(client, engine):
    assert client.get("/api/v1/biomarkers/nope/history").status_code == 404


def test_unit_mismatch_flagged(client, engine):
    seed(engine)
    with Session(engine) as s:
        rep = LabReport(test_date=dt.date(2025, 1, 1))
        s.add(rep)
        s.flush()
        s.add(Biomarker(report_id=rep.id, marker_key="vitamin_d_25_oh", display_name="Vitamin D",
                        raw_name="Vit D", value=80, unit="nmol/L"))
        s.commit()
    assert client.get("/api/v1/biomarkers/vitamin_d_25_oh/history").json()["unit_mismatch"] is True


def test_marker_summaries(client, engine):
    seed(engine)
    rows = {r["marker_key"]: r for r in client.get("/api/v1/biomarkers").json()}
    assert rows["vitamin_d_25_oh"]["count"] == 3 and rows["vitamin_d_25_oh"]["latest_value"] == 31
    assert (rows["vitamin_d_25_oh"]["ref_min"], rows["vitamin_d_25_oh"]["ref_max"]) == (30, 100)
    assert rows["unmapped:mucus"]["latest_text"] == "+" and rows["unmapped:mucus"]["count"] == 0


def test_compare_normalizes_to_reference_range(client, engine):
    seed(engine)
    r = client.get("/api/v1/biomarkers/compare",
                   params={"keys": "vitamin_d_25_oh", "dates": "2022-01-15,2024-03-01"}).json()
    vals = r["vitamin_d_25_oh"]
    assert [v["value"] for v in vals] == [18, 31]
    assert round(vals[1]["pct_of_range"], 3) == round((31 - 30) / 70, 3)
    assert vals[0]["pct_of_range"] < 0  # below ref_min


def test_context_overlay(client, engine):
    seed(engine)
    c = client.get("/api/v1/context", params={"from": "2023-01-01", "to": "2023-12-31"}).json()
    assert [m["name"] for m in c["medications"]] == ["Креон"]
    assert [r["title"] for r in c["records"]] == ["Визит к урологу"]


def test_review_alias_back_applies_and_date_confirm(client, engine):
    seed(engine)
    assert client.get("/api/v1/review/unmapped").json() == [{"raw_name": "Mucus", "count": 1, "latest_value": None,
                                                                   "latest_date": "2024-03-01", "unit": ""}]
    r = client.post("/api/v1/review/alias", json={"raw_name": "Mucus", "marker_key": "mucus",
                                                  "display_name": "Mucus"})
    assert r.status_code == 200
    assert client.get("/api/v1/review/unmapped").json() == []
    assert "mucus" in {m["marker_key"] for m in client.get("/api/v1/biomarkers").json()}
    sus_id = [x for x in client.get("/api/v1/records").json() if x["date_suspect"]][0]["id"]
    assert client.post("/api/v1/review/date", json={"record_id": sus_id, "confirmed_date": "2022-01-15"}).status_code == 200
    assert not [x for x in client.get("/api/v1/records").json() if x["date_suspect"]]


def test_empty_unit_mixed_with_real_unit_is_a_mismatch(client, engine):
    seed(engine)
    with Session(engine) as s:
        rep = LabReport(test_date=dt.date(2025, 1, 1))
        s.add(rep)
        s.flush()
        s.add(Biomarker(report_id=rep.id, marker_key="vitamin_d_25_oh", display_name="Vitamin D",
                        raw_name="Vit D", value=30, unit=""))
        s.commit()
    assert client.get("/api/v1/biomarkers/vitamin_d_25_oh/history").json()["unit_mismatch"] is True


def test_range_mismatch_between_labs_is_flagged(client, engine):
    seed(engine)
    assert client.get("/api/v1/biomarkers/vitamin_d_25_oh/history").json()["range_mismatch"] is False
    with Session(engine) as s:
        rep = LabReport(test_date=dt.date(2025, 1, 1))
        s.add(rep)
        s.flush()
        s.add(Biomarker(report_id=rep.id, marker_key="vitamin_d_25_oh", display_name="Vitamin D",
                        raw_name="Vit D", value=30, unit="ng/mL", ref_min=20, ref_max=50))
        s.commit()
    assert client.get("/api/v1/biomarkers/vitamin_d_25_oh/history").json()["range_mismatch"] is True


def _demo_marker(engine):
    with Session(engine) as s:
        rep = LabReport(test_date=dt.date(2025, 1, 1), source="demo")
        s.add(rep)
        s.flush()
        s.add(Biomarker(report_id=rep.id, marker_key="ferritin", display_name="Ferritin", raw_name="Ferritin", value=85,
                        unit="ng/mL", ref_min=30, ref_max=400, source="demo"))
        s.add(MedicalRecord(title="Demo visit", record_type="visit", record_date=dt.date(2025, 2, 1), source="demo",
                            external_id="d1"))
        s.commit()


def test_demo_rows_are_marked_in_summaries_history_and_records(client, engine):
    seed(engine)
    _demo_marker(engine)
    summaries = {m["marker_key"]: m for m in client.get("/api/v1/biomarkers").json()}
    assert summaries["ferritin"]["is_demo"] is True and summaries["vitamin_d_25_oh"]["is_demo"] is False
    points = client.get("/api/v1/biomarkers/ferritin/history").json()["points"]
    assert [p["is_demo"] for p in points] == [False, True]
    records = {r["title"]: r for r in client.get("/api/v1/records").json()}
    assert records["Demo visit"]["is_demo"] is True and records["Old panel"]["is_demo"] is False
