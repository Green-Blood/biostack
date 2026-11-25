import datetime as dt
import io
import zipfile

from sqlmodel import select

from db.models import DailyMetric
from services.apple_health_import import import_apple_health_zip, looks_like_apple_health_zip


def _make_apple_zip(xml_body: str, entry_name: str = "apple_health_export/export.xml") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(entry_name, xml_body.encode("utf-8"))
    return buf.getvalue()


SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="en_US">
  <Record type="HKQuantityTypeIdentifierStepCount" unit="count" startDate="2026-11-10 08:00:00 +0500" endDate="2026-11-10 09:00:00 +0500" value="3200"/>
  <Record type="HKQuantityTypeIdentifierStepCount" unit="count" startDate="2026-11-10 18:00:00 +0500" endDate="2026-11-10 19:00:00 +0500" value="4800"/>
  <Record type="HKQuantityTypeIdentifierDistanceWalkingRunning" unit="km" startDate="2026-11-10 08:00:00 +0500" endDate="2026-11-10 09:00:00 +0500" value="5.4"/>
  <Record type="HKQuantityTypeIdentifierActiveEnergyBurned" unit="kcal" startDate="2026-11-10 08:00:00 +0500" endDate="2026-11-10 09:00:00 +0500" value="340.5"/>
  <Record type="HKQuantityTypeIdentifierRestingHeartRate" unit="count/min" startDate="2026-11-10 07:00:00 +0500" endDate="2026-11-10 07:05:00 +0500" value="56"/>
  <Record type="HKQuantityTypeIdentifierRestingHeartRate" unit="count/min" startDate="2026-11-10 20:00:00 +0500" endDate="2026-11-10 20:05:00 +0500" value="60"/>
  <Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" unit="ms" startDate="2026-11-10 06:00:00 +0500" endDate="2026-11-10 06:05:00 +0500" value="64.0"/>
  <Record type="HKQuantityTypeIdentifierOxygenSaturation" unit="%" startDate="2026-11-10 05:00:00 +0500" endDate="2026-11-10 05:05:00 +0500" value="0.98"/>
  <Record type="HKCategoryTypeIdentifierSleepAnalysis" startDate="2026-11-09 23:00:00 +0500" endDate="2026-11-10 03:00:00 +0500" value="HKCategoryValueSleepAnalysisAsleepCore"/>
  <Record type="HKCategoryTypeIdentifierSleepAnalysis" startDate="2026-11-10 03:00:00 +0500" endDate="2026-11-10 04:30:00 +0500" value="HKCategoryValueSleepAnalysisAsleepDeep"/>
  <Record type="HKCategoryTypeIdentifierSleepAnalysis" startDate="2026-11-10 04:30:00 +0500" endDate="2026-11-10 06:00:00 +0500" value="HKCategoryValueSleepAnalysisAsleepREM"/>
  <Record type="HKCategoryTypeIdentifierSleepAnalysis" startDate="2026-11-10 06:00:00 +0500" endDate="2026-11-10 06:30:00 +0500" value="HKCategoryValueSleepAnalysisAwake"/>
</HealthData>
"""


def test_import_apple_health_zip_parses_metrics_and_is_idempotent(session, tmp_path):
    zip_file = tmp_path / "apple-export.zip"
    zip_file.write_bytes(_make_apple_zip(SAMPLE_XML))
    assert looks_like_apple_health_zip(zip_file)

    first = import_apple_health_zip(session, zip_file)
    assert first == {"days_written": 1, "fields_written": 12, "records_scanned": 12, "sleep_nights": 1}

    row = session.exec(select(DailyMetric).where(DailyMetric.metric_date == dt.date(2026, 11, 10))).one()
    assert row.steps == 8000
    assert row.distance_m == 5400.0
    assert row.active_kcal == 340.5
    assert row.resting_hr == 58.0
    assert row.hrv_sdnn == 64.0
    assert row.spo2_avg == 98.0
    assert row.sleep_light_min == 240.0
    assert row.sleep_deep_min == 90.0
    assert row.sleep_rem_min == 90.0
    assert row.sleep_awake_min == 30.0
    assert row.sleep_total_min == 420.0
    assert row.sleep_efficiency == 93.3

    second = import_apple_health_zip(session, zip_file)
    assert second["days_written"] == 1
    assert session.exec(select(DailyMetric)).all() == [row]


def test_apple_health_upload_api_and_invalid_zip(client, tmp_path, monkeypatch):
    monkeypatch.setattr("config.settings.data_dir", tmp_path)

    bad = client.post(
        "/api/v1/imports/apple-health",
        files={"file": ("not-apple.zip", _make_apple_zip("<root/>", "other.xml"), "application/zip")},
    )
    assert bad.status_code == 415

    good = client.post(
        "/api/v1/imports/apple-health",
        files={"file": ("export.zip", _make_apple_zip(SAMPLE_XML), "application/zip")},
    )
    assert good.status_code == 200
    assert good.json()["days_written"] == 1
    assert good.json()["sleep_nights"] == 1
    assert not list((tmp_path / "tmp").glob("apple-*.zip"))
