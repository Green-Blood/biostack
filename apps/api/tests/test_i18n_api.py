import datetime as dt
import hashlib

import pytest
from sqlmodel import Session

from config import settings
from db.models import LabReport
from services import i18n

RU = {"Accept-Language": "ru"}
EN = {"Accept-Language": "en"}


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)


def _manual(client, name="Vitamin D"):
    body = {"test_date": "2025-01-10", "lab_name": "", "rows": [
        {"name": name, "value": 18, "unit": "ng/mL", "ref_min": 30, "ref_max": 100}]}
    assert client.post("/api/v1/labs/manual", json=body).status_code == 201


def test_not_found_details_follow_the_language_header(client):
    path = "/api/v1/journal/999"
    for headers in ({}, EN):
        assert client.delete(path, headers=headers).json()["detail"] == "No such journal entry"
    assert client.delete(path, headers=RU).json()["detail"] == i18n.msg("ru", "http.journal_not_found")
    assert i18n.msg("ru", "http.journal_not_found") != "No such journal entry"
    assert client.get("/api/v1/records/999", headers=RU).json()["detail"] == i18n.msg("ru", "http.record_not_found")


def test_the_lab_duplicate_409_keeps_its_structure_in_russian(client, engine):
    pdf = b"%PDF-1.4 same file"
    with Session(engine) as session:
        session.add(LabReport(test_date=dt.date(2025, 1, 1), lab_name="x", source="pdf", file_hash=hashlib.sha256(pdf).hexdigest()))
        session.commit()
    ru = client.post("/api/v1/labs/upload", files={"file": ("a.pdf", pdf)}, headers=RU)
    en = client.post("/api/v1/labs/upload", files={"file": ("a.pdf", pdf)})
    assert ru.status_code == en.status_code == 409
    assert en.json()["detail"]["message"] == "This file is already saved."
    assert ru.json()["detail"]["message"] == i18n.msg("ru", "http.lab_already_saved")
    assert ru.json()["detail"]["report_id"] == en.json()["detail"]["report_id"]


def test_unsupported_upload_in_russian(client):
    res = client.post("/api/v1/labs/upload", files={"file": ("a.txt", b"hello")}, headers=RU)
    assert res.status_code == 415
    assert res.json()["detail"] == i18n.msg("ru", "http.lab_bad_type")


def test_oversized_upload_message_carries_the_limit(client, monkeypatch):
    monkeypatch.setattr("routers.lab_uploads.MAX_UPLOAD_BYTES", 1024 * 1024)
    res = client.post("/api/v1/labs/upload", files={"file": ("a.pdf", b"%PDF" + b"0" * 2 * 1024 * 1024)}, headers=RU)
    assert res.status_code == 413
    assert res.json()["detail"] == i18n.msg("ru", "http.lab_too_large", mb=1)


def test_ai_off_refresh_in_russian(client):
    res = client.post("/api/v1/analytics/briefing/refresh", headers=RU)
    assert res.status_code == 409
    assert res.json()["detail"] == i18n.msg("ru", "http.ai_off")
    assert client.post("/api/v1/analytics/briefing/refresh").json()["detail"] == "AI summaries are off. Turn them on in Settings first."


def test_location_error_from_the_service_is_translated(client):
    res = client.post("/api/v1/environment/refresh", headers=RU)
    assert res.status_code == 409
    assert res.json()["detail"] == i18n.msg("ru", "env.location_not_set")


def test_marker_names_are_russian_across_biomarker_endpoints(client):
    _manual(client)
    assert client.get("/api/v1/biomarkers").json()[0]["display_name"] == "Vitamin D (25-OH)"
    assert client.get("/api/v1/biomarkers", headers=RU).json()[0]["display_name"] == "Витамин D (25-OH)"
    en = client.get("/api/v1/biomarkers/vitamin_d_25_oh/history").json()
    ru = client.get("/api/v1/biomarkers/vitamin_d_25_oh/history", headers=RU).json()
    assert (en["display_name"], ru["display_name"]) == ("Vitamin D (25-OH)", "Витамин D (25-OH)")
    assert client.get("/api/v1/biomarkers/nope/history", headers=RU).json()["detail"] == i18n.msg("ru", "http.marker_unknown")


def test_manual_save_response_and_unmapped_markers_localize(client):
    body = {"test_date": "2025-01-10", "lab_name": "", "rows": [
        {"name": "Ferritin", "value": 5, "unit": "ng/mL"}, {"name": "Mucus", "value": 1, "unit": "x"}]}
    res = client.post("/api/v1/labs/manual", json=body, headers=RU).json()
    assert {m["display_name"] for m in res["markers"]} == {"Ферритин", "Mucus"}


def test_analytics_texts_come_back_in_russian(client):
    en = client.get("/api/v1/analytics/risk").json()
    ru = client.get("/api/v1/analytics/risk", headers=RU).json()
    assert en["reason"].startswith("Only 0 of 6")
    assert ru["reason"] == i18n.msg("ru", "ew.reason", n=0, total=6, min=2)
    assert client.get("/api/v1/analytics/briefing", headers=RU).json()["label"] == i18n.msg("ru", "briefing.fallback_label")
    assert client.get("/api/v1/analytics/graph", headers=RU).json()["notes"] == [i18n.msg("ru", "graph.not_run")]
