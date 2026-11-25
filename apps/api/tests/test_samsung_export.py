import datetime as dt
import zipfile

import pytest

from services import samsung_export as se
from tests.samsung_fixture import build_export, default_tables, tables_copy

UTC = dt.UTC


@pytest.fixture
def export_path(tmp_path):
    return build_export(tmp_path / "Samsung Health.zip")


@pytest.fixture
def export(export_path):
    return se.read_export(export_path)


def test_offset_parsing():
    assert se.parse_offset("UTC+0500") == 300
    assert se.parse_offset("UTC-0400") == -240
    assert se.parse_offset("UTC+0530") == 330
    with pytest.raises(ValueError):
        se.parse_offset("+5")


def test_timestamps_are_utc_and_offset_moves_local_day(export):
    late = next(s for s in export.stress if s.score == 35)
    assert late.start_utc == dt.datetime(2026, 10, 2, 20, 30, tzinfo=UTC)
    assert late.tz_min == 300
    assert late.local_date == dt.date(2026, 10, 3)  # 20:30 UTC at +0500 is 01:30 the next day
    west = next(s for s in export.stress if s.score == 22)
    assert west.tz_min == -240 and west.local_date == dt.date(2026, 10, 2)
    hr = next(h for h in export.hr if h.hr == 61)
    assert hr.local_date == dt.date(2026, 10, 3) and hr.min is None


def test_sleep_session_wake_date_and_fields(export):
    main = next(s for s in export.sleep if s.uuid.endswith("01"))
    assert main.start_utc == dt.datetime(2026, 10, 1, 22, 0, tzinfo=UTC)
    assert main.end_utc == dt.datetime(2026, 10, 2, 5, 0, tzinfo=UTC)
    assert main.wake_date == dt.date(2026, 10, 2)
    assert (main.efficiency, main.sleep_type, main.device) == (91.5, "-1", "dev-watch")
    nap = next(s for s in export.sleep if s.uuid.endswith("02"))
    assert nap.efficiency is None and nap.sleep_type == "3"


def test_stage_codes_are_mapped(export):
    assert [s.stage for s in sorted(export.stages, key=lambda s: s.start_utc)] == ["awake", "light", "deep", "rem"]
    assert {s.sleep_uuid for s in export.stages} == {"aaaaaaaa-0000-4000-8000-000000000001"}


def test_hrv_bins_read_from_json(export):
    assert [(b.value, b.value2) for b in export.hrv] == [(41.2, 35.0), (45.8, 38.4)]
    assert export.hrv[0].start_utc == dt.datetime(2026, 10, 1, 22, 0, tzinfo=UTC)
    assert export.hrv[0].end_utc == dt.datetime(2026, 10, 1, 22, 5, tzinfo=UTC)
    assert export.hrv[0].tz_min == 300


def test_skin_and_respiratory(export):
    assert [(b.value, b.value2) for b in export.skin] == [(33.8, 33.6)]  # bin mean + the row's baseline
    # one row with detail (two bins) and one without (the row's average)
    assert sorted(b.value for b in export.resp) == [14.2, 14.8, 15.0]


def test_spo2_hr_workouts_body(export):
    assert [(o.spo2, o.min) for o in export.spo2] == [(96.0, 92.0)]
    run = next(w for w in export.workouts if w.uuid == "ex-1")
    assert (run.type_code, run.duration_min, run.kcal, run.distance_m, run.hr_avg, run.hr_max, run.device) == \
        (1001, 45.0, 250.5, 4100.0, 118.0, 141.0, "dev-watch")
    other = next(w for w in export.workouts if w.uuid == "ex-2")
    assert (other.type_code, other.duration_min, other.kcal, other.distance_m) == (0, 30.0, 90.0, None)
    kinds = {b.kind: b.value for b in export.body}
    assert kinds == {"weight": 80.5, "body_fat_pct": 20.1, "muscle_kg": 52.0, "bmr_kcal": 1750.0, "visceral_fat": 9.0,
                     "skeletal_muscle_kg": 35.2}
    assert export.latest_height_cm == 181.0


def test_steps_deduped_across_sources_keeping_max(export):
    by_day = {s.local_date: s for s in export.steps}
    assert set(by_day) == {dt.date(2026, 10, 2), dt.date(2026, 10, 3)}
    assert (by_day[dt.date(2026, 10, 2)].steps, by_day[dt.date(2026, 10, 2)].distance_m,
            by_day[dt.date(2026, 10, 2)].kcal) == (8000, 5600.5, 310.2)
    assert by_day[dt.date(2026, 10, 3)].steps == 4321


def test_unknown_type_listed_as_not_imported(export):
    assert export.skipped["food_intake"] == "not imported"
    assert "sleep" not in export.skipped


def test_counts(export):
    assert export.counts["sleep"] == 2 and export.counts["stages"] == 4 and export.counts["hrv"] == 2
    assert export.counts["steps"] == 2 and export.counts["workouts"] == 2 and export.counts["body"] == 6


def test_missing_required_column_skips_only_that_type(tmp_path):
    tables = default_tables()
    tables["tracker.heart_rate"].bare.remove("heart_rate")
    tables["sleep_stage"].bare.remove("stage")
    export = se.read_export(build_export(tmp_path / "x.zip", tables))
    assert export.hr == [] and "heart_rate" in export.skipped["tracker.heart_rate"]
    assert export.stages == [] and "stage" in export.skipped["sleep_stage"]
    assert len(export.sleep) == 2 and len(export.stress) == 2  # the rest imports


def test_missing_time_offset_uses_default(tmp_path):
    tables = default_tables()
    tables["stress"].qualified.remove("time_offset")
    export = se.read_export(build_export(tmp_path / "x.zip", tables), default_tz_min=180)
    assert {s.tz_min for s in export.stress} == {180}


def test_junk_rows_skipped_and_counted(tmp_path):
    tables = default_tables()
    tables["stress"].rows.append(dict(start_time="not a date", time_offset="UTC+0500", datauuid="sr-x", score="5"))
    tables["stress"].rows.append(dict(start_time="2026-10-02 10:00:00.000", time_offset="UTC+0500",
                                      datauuid="sr-y", score="n/a"))
    tables["sleep_stage"].rows.append(dict(start_time="2026-10-02 05:00:00.000", end_time="2026-10-02 05:10:00.000",
                                           time_offset="UTC+0500", datauuid="st-x", sleep_id="s", stage="49999"))
    export = se.read_export(build_export(tmp_path / "x.zip", tables))
    assert len(export.stress) == 2 and export.junk["stress"] == 2
    assert len(export.stages) == 4 and export.junk["sleep_stage"] == 1


def test_short_and_ragged_rows_do_not_break_the_type(tmp_path):
    export_path = tmp_path / "x.zip"
    build_export(export_path)
    # append a truncated line to the stress CSV
    with zipfile.ZipFile(export_path) as zf:
        members = {i.filename: zf.read(i) for i in zf.infolist()}
    name = next(n for n in members if ".stress." in n)
    members[name] += b"2026-10-02 11:00:00.000\n\n"
    with zipfile.ZipFile(export_path, "w") as zf:
        for n, data in members.items():
            zf.writestr(n, data)
    export = se.read_export(export_path)
    assert len(export.stress) == 2 and export.junk["stress"] == 1


def test_progress_reaches_one(export_path):
    seen: list[tuple[float, str]] = []
    se.read_export(export_path, progress=lambda f, stage: seen.append((f, stage)))
    fractions = [f for f, _ in seen]
    assert fractions[-1] == 1.0
    assert fractions == sorted(fractions) and all(0.0 <= f <= 1.0 for f in fractions)
    assert len(seen) > 3


def test_never_more_than_one_member_open(export_path, monkeypatch):
    real_open = zipfile.ZipFile.open
    state = {"open": 0, "max": 0, "calls": 0}

    class Tracked:
        def __init__(self, inner):
            self._inner = inner
            self._closed = False

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def __iter__(self):
            return iter(self._inner)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()

        def close(self):
            if not self._closed:
                self._closed = True
                state["open"] -= 1
            self._inner.close()

    def tracking_open(self, name, mode="r", *args, **kwargs):
        handle = real_open(self, name, mode, *args, **kwargs)
        if mode != "r":
            return handle
        state["open"] += 1
        state["calls"] += 1
        state["max"] = max(state["max"], state["open"])
        return Tracked(handle)

    monkeypatch.setattr(zipfile.ZipFile, "open", tracking_open)
    export = se.read_export(export_path)
    assert len(export.hrv) == 2  # the JSON members were read
    assert state["calls"] > 5
    assert state["max"] == 1
    assert state["open"] == 0


def test_oversized_field_drops_only_that_row_and_csv_limit_is_untouched(tmp_path):
    import csv
    before = csv.field_size_limit()
    tables = default_tables()
    tables["exercise"].rows.append(dict(start_time="2026-10-04 12:00:00.000", end_time="2026-10-04 12:30:00.000",
                                        time_offset="UTC+0500", datauuid="ex-big", exercise_type="1001",
                                        live_data="x" * (before + 10)))
    tables["exercise"].rows.append(dict(start_time="2026-10-05 12:00:00.000", end_time="2026-10-05 12:30:00.000",
                                        time_offset="UTC+0500", datauuid="ex-3", exercise_type="1002"))
    export = se.read_export(build_export(tmp_path / "x.zip", tables))
    assert {w.uuid for w in export.workouts} == {"ex-1", "ex-2", "ex-3"}
    assert export.junk["exercise"] >= 1
    assert csv.field_size_limit() == before


def test_heart_rate_detail_bins_replace_the_hourly_row(export):
    from tests.samsung_fixture import HR_DETAIL_ID
    assert HR_DETAIL_ID  # the fixture row with detail
    values = sorted(h.hr for h in export.hr)
    assert 58 not in values  # the hourly summary row was replaced by its bins
    assert len(values) == 25 + 3 and set(values) == {49.0, 50.0, 51.0, 52.0, 61.0, 77.0}  # bins, hr-1, hr-2, no-detail
    first = min((h for h in export.hr if h.hr in (49.0, 50.0, 51.0)), key=lambda h: h.start_utc)
    assert first.start_utc == dt.datetime(2026, 10, 2, 0, 0, tzinfo=UTC)
    assert first.end_utc == dt.datetime(2026, 10, 2, 0, 0, 59, tzinfo=UTC)
    assert first.tz_min == 300 and first.min == 47.0
    assert export.junk["tracker.heart_rate"] == 1  # the zero bin


def test_hourly_heart_rate_fallback_rejects_non_positive(tmp_path):
    tables = tables_copy()
    tables["tracker.heart_rate"].rows += [
        dict(start_time="2026-10-02 11:00:00.000", end_time="2026-10-02 11:59:59.000", time_offset="UTC+0500",
             datauuid="hr-zero", heart_rate="0", min="", max="", binning_data=""),
        dict(start_time="2026-10-02 12:00:00.000", end_time="2026-10-02 12:59:59.000", time_offset="UTC+0500",
             datauuid="hr-neg", heart_rate="-5", min="", max="", binning_data=""),
    ]
    export = se.read_export(build_export(tmp_path / "x.zip", tables))
    assert all(h.hr > 0 for h in export.hr)
    assert export.junk["tracker.heart_rate"] == 1 + 2  # the zero bin + two rows


def test_heart_rate_row_with_empty_value_but_detail_file_is_read(tmp_path):
    from tests.samsung_fixture import HR_SUFFIX, _ms, default_jsons
    uuid = "abababab-0000-4000-8000-000000000001"
    tables = tables_copy()
    tables["tracker.heart_rate"].rows.append(
        dict(start_time="2026-10-03 00:00:00.000", end_time="2026-10-03 00:59:59.000", time_offset="UTC+0500",
             datauuid=uuid, heart_rate="", min="", max="", binning_data=f"{uuid}{HR_SUFFIX}"))
    jsons = default_jsons()
    jsons[("tracker.heart_rate", uuid)] = [dict(start_time=_ms("2026-10-03 00:00:00"),
                                                end_time=_ms("2026-10-03 00:00:59"), heart_rate=63.0,
                                                heart_rate_min=60.0, heart_rate_max=66.0)]
    export = se.read_export(build_export(tmp_path / "x.zip", tables, jsons))
    assert 63.0 in [h.hr for h in export.hr]
    assert export.junk["tracker.heart_rate"] == 1  # only the fixture's zero bin
