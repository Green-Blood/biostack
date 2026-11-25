import datetime as dt
import json

from db.models import Biomarker, LabReport


def test_settings_default_to_no_location_and_2300(client):
    body = client.get("/api/v1/settings").json()
    assert (body["latitude"], body["longitude"], body["bedtime"], body["timezone"], body["ai_briefing"]) == (None, None, "23:00", "", False)
    assert body["detected_timezone"]


def test_settings_round_trip(client):
    mine = {"latitude": 52.52, "longitude": 13.41, "bedtime": "22:30", "timezone": "Europe/Berlin", "ai_briefing": True}
    assert client.put("/api/v1/settings", json=mine).json() == {**mine, "detected_timezone": client.get("/api/v1/settings").json()["detected_timezone"]}
    assert {k: client.get("/api/v1/settings").json()[k] for k in mine} == mine


def test_timezone_must_be_a_known_iana_name(client):
    base = {"latitude": None, "longitude": None, "bedtime": "23:00"}
    assert client.put("/api/v1/settings", json={**base, "timezone": "Mars/Olympus"}).status_code == 422


def test_location_must_be_a_real_coordinate_pair(client):
    assert client.put("/api/v1/settings", json={"latitude": 95, "longitude": 0, "bedtime": "23:00"}).status_code == 422
    assert client.put("/api/v1/settings", json={"latitude": 10, "longitude": None, "bedtime": "23:00"}).status_code == 422


def test_bedtime_must_be_a_clock_time(client):
    assert client.put("/api/v1/settings", json={"latitude": None, "longitude": None, "bedtime": "25:99"}).status_code == 422
    assert client.put("/api/v1/settings", json={"latitude": None, "longitude": None, "bedtime": "late"}).status_code == 422


def test_export_contains_every_table_as_json(client, session):
    report = LabReport(test_date=dt.date(2026, 1, 2), lab_name="Lab")
    session.add(report)
    session.commit()
    session.add(Biomarker(report_id=report.id, marker_key="ferritin", display_name="Ferritin", value=50))
    session.commit()
    res = client.get("/api/v1/settings/export")
    assert res.status_code == 200 and "attachment" in res.headers["content-disposition"]
    data = json.loads(res.content)
    assert data["labreport"][0]["lab_name"] == "Lab" and data["biomarker"][0]["marker_key"] == "ferritin"
    assert {"supplementlog", "healthjournal", "cnstest", "dailymetric", "appsetting"} <= data.keys()


def test_patch_changes_only_the_fields_sent(client):
    client.put("/api/v1/settings", json={"latitude": 1.0, "longitude": 2.0, "bedtime": "22:00", "timezone": "Europe/Berlin"})
    body = client.patch("/api/v1/settings", json={"ai_briefing": True}).json()
    assert (body["ai_briefing"], body["bedtime"], body["timezone"], body["latitude"]) == (True, "22:00", "Europe/Berlin", 1.0)
    assert client.patch("/api/v1/settings", json={"bedtime": "late"}).status_code == 422
    assert client.get("/api/v1/settings").json()["bedtime"] == "22:00"


def test_archive_zip_has_readable_files_and_originals(client, session, tmp_path, monkeypatch):
    import io, zipfile
    from config import settings
    from db.models import MedicalRecord, RecordAttachment
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    (tmp_path / "attachments").mkdir()
    (tmp_path / "attachments" / "abc.pdf").write_bytes(b"%PDF-1.4 test")
    record = MedicalRecord(title="Visit", record_date=dt.date(2026, 1, 2))
    report = LabReport(test_date=dt.date(2026, 1, 2), lab_name="Lab")
    session.add_all([record, report]); session.commit()
    session.add_all([Biomarker(report_id=report.id, marker_key="ferritin", display_name="Ferritin", value=50, unit="ng/mL"),
                     RecordAttachment(record_id=record.id, filename="my scan.pdf", stored_path="attachments/abc.pdf", mime_type="application/pdf", size_bytes=13, sha256="x")])
    session.commit()
    res = client.get("/api/v1/settings/export/archive")
    assert res.status_code == 200 and res.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(res.content))
    names = set(z.namelist())
    assert {"README.md", "profile.md", "records.md", "biomarkers.csv", "courses.csv", "data/all-tables.json"} <= names
    assert f"files/{record.id}-my scan.pdf" in names
    assert "Ferritin" in z.read("biomarkers.csv").decode() and "Visit" in z.read("records.md").decode()
