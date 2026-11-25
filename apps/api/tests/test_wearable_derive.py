import datetime as dt
import time

from services import samsung_export as se
from services import wearable_derive as wd
from services.samsung_export import (BinRec, BodyRec, Export, HrRec, SleepRec, SpO2Rec, StageRec, StepsDay, StressRec,
                                     WorkoutRec)
from services.wearable_ingest import SleepIn, StageIn, WorkoutIn
from tests.samsung_fixture import build_export, tables_copy

UTC = dt.UTC
D = dt.date


def t(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text).replace(tzinfo=UTC)


def night(uuid, start, end, tz=300, sleep_type="-1", eff=None, device="watch"):
    return SleepRec(uuid, t(start), t(end), tz, sleep_type, eff, device)


def by_id(sessions: list[SleepIn]) -> dict[str, SleepIn]:
    return {s.external_id: s for s in sessions}


def hr_run(start: str, values: list[float], every_min: int = 1, length_min: int = 1, tz: int = 300) -> list[HrRec]:
    """HR readings `every_min` apart, each `length_min` long (default: back-to-back one-minute bins, as Samsung's
    heart-rate detail files hold)."""
    s = t(start)
    return [HrRec(s + dt.timedelta(minutes=i * every_min), s + dt.timedelta(minutes=i * every_min + length_min), tz,
                  v, None) for i, v in enumerate(values)]


# ---------------------------------------------------------------- derive_sleep

def test_night_crossing_midnight_with_plus_five_wakes_on_local_end_date():
    # 20:00 UTC = 01:00 local next day; 02:30 UTC = 07:30 local; wake date is the local date of the end
    rec = night("n1", "2026-10-01 20:00:00", "2026-10-02 02:30:00")
    stages = [StageRec("s1", "n1", t("2026-10-01 20:00:00"), t("2026-10-01 20:10:00"), "awake"),
              StageRec("s2", "n1", t("2026-10-01 20:10:00"), t("2026-10-01 22:00:00"), "light"),
              StageRec("s3", "n1", t("2026-10-01 22:00:00"), t("2026-10-02 00:00:00"), "deep"),
              StageRec("s4", "n1", t("2026-10-02 00:00:00"), t("2026-10-02 02:30:00"), "rem")]
    sessions, by_session = wd.derive_sleep([rec], stages)
    (s,) = sessions
    assert isinstance(s, SleepIn)
    assert s.wake_date == D(2026, 10, 2) and s.tz_offset_min == 300
    assert s.duration_min == 390 and s.awake_min == 10 and s.light_min == 110 and s.deep_min == 120 and s.rem_min == 150
    assert s.is_main and s.device_id == "watch" and s.sleep_type == "-1"
    assert [st.external_id for st in by_session["n1"]] == ["s1", "s2", "s3", "s4"]
    assert all(isinstance(st, StageIn) for st in by_session["n1"])


def test_west_offset_night_wake_date():
    # 03:00 UTC at -0400 is 23:00 the previous local day
    rec = night("w", "2026-10-01 20:00:00", "2026-10-02 03:00:00", tz=-240)
    (s,), _ = wd.derive_sleep([rec], [])
    assert s.wake_date == D(2026, 10, 1)


def test_nap_and_overlapping_duplicate_one_main_per_wake_date():
    main = night("main", "2026-10-01 18:00:00", "2026-10-02 02:00:00")  # 8 h
    dup = night("dup", "2026-10-01 18:30:00", "2026-10-02 01:30:00", device="phone")  # 7 h, overlaps fully
    nap = night("nap", "2026-10-02 09:00:00", "2026-10-02 09:40:00", sleep_type="3")
    sessions, _ = wd.derive_sleep([dup, nap, main], [])
    s = by_id(sessions)
    assert s["main"].is_main and not s["dup"].is_main and not s["nap"].is_main
    assert {x.wake_date for x in sessions} == {D(2026, 10, 2)}


def test_overlapping_duplicate_on_a_different_wake_date_is_not_main():
    # the shorter recording ends before local midnight (+0500): a different wake date, but >50 % overlap
    main = night("main", "2026-10-01 17:00:00", "2026-10-02 01:00:00")  # wakes 2026-10-02 06:00 local
    short = night("short", "2026-10-01 17:00:00", "2026-10-01 18:30:00")  # 23:30 local on 2026-10-01
    sessions, _ = wd.derive_sleep([short, main], [])
    s = by_id(sessions)
    assert s["main"].is_main and not s["short"].is_main


def test_small_overlap_is_one_night_on_the_later_wake_date():
    # (was a 19.5 h part b; the night-length guard keeps merged nights within 18 h, so the shape is kept, shorter)
    a = night("a", "2026-10-02 08:00:00", "2026-10-02 16:00:00")  # ends 10-02 local (21:00)
    b = night("b", "2026-10-02 15:30:00", "2026-10-02 21:00:00")  # ends 10-03 local (02:00); 30 min overlap
    s = by_id(wd.derive_sleep([a, b], [])[0])
    assert s["a"].is_main and s["b"].is_main
    assert s["a"].wake_date == s["b"].wake_date == D(2026, 10, 3)


def test_separate_nights_on_consecutive_dates_stay_separate():
    a = night("a", "2026-10-01 18:00:00", "2026-10-02 02:00:00")  # wakes 10-02
    b = night("b", "2026-10-02 18:00:00", "2026-10-03 02:00:00")  # wakes 10-03, 16 h later
    s = by_id(wd.derive_sleep([a, b], [])[0])
    assert s["a"].is_main and s["b"].is_main
    assert (s["a"].wake_date, s["b"].wake_date) == (D(2026, 10, 2), D(2026, 10, 3))


def test_gap_just_over_limit_on_consecutive_dates_stays_separate():
    a = night("a", "2026-10-01 17:00:00", "2026-10-01 18:00:00")  # 23:00 local 10-01
    b = night("b", "2026-10-01 21:01:00", "2026-10-02 02:00:00")  # 181 min later, wakes 10-02
    s = by_id(wd.derive_sleep([a, b], [])[0])
    assert s["a"].is_main and s["b"].is_main
    assert (s["a"].wake_date, s["b"].wake_date) == (D(2026, 10, 1), D(2026, 10, 2))


def test_chain_of_parts_never_spans_more_than_18_hours():
    # night, three daytime (non-nap) sleeps each within 3 h of the last, then the next night: the chain must not
    # swallow both nights into one
    parts = [night("n1", "2026-10-01 22:00:00", "2026-10-02 06:00:00", tz=0),
             night("d1", "2026-10-02 08:00:00", "2026-10-02 09:00:00", tz=0),
             night("d2", "2026-10-02 12:00:00", "2026-10-02 13:00:00", tz=0),
             night("d3", "2026-10-02 16:00:00", "2026-10-02 17:00:00", tz=0),
             night("n2", "2026-10-02 20:00:00", "2026-10-03 04:00:00", tz=0)]
    s = by_id(wd.derive_sleep(parts, [])[0])
    assert s["n1"].is_main and s["n2"].is_main
    assert s["n1"].wake_date == D(2026, 10, 2) and s["n2"].wake_date == D(2026, 10, 3)
    assert s["d3"].wake_date == D(2026, 10, 3)  # 22:00 -> 17:00 would be 19 h: d3 starts the next chain


def test_night_split_across_local_midnight_is_one_night():
    # +0500: 22:00-23:50 local (10-01), then 01:30-07:00 local (10-02): one night on 10-02
    ex = Export()
    ex.sleep = [night("A", "2026-10-01 17:00:00", "2026-10-01 18:50:00"),
                night("B", "2026-10-01 20:30:00", "2026-10-02 02:00:00")]
    sessions, _ = wd.derive_sleep(ex.sleep, [])
    s = by_id(sessions)
    assert s["A"].is_main and s["B"].is_main and s["A"].wake_date == s["B"].wake_date == D(2026, 10, 2)
    days = wd.derive_days(ex, sessions)
    assert days == {D(2026, 10, 2): {"sleep_total_min": 110 + 330}}


def test_westward_split_night_takes_the_wake_date_of_the_part_ending_last():
    # A at +0500 ends 03:00 local 10-02; B at -0400 ends later in UTC but on 23:30 local 10-01: the night is 10-01
    ex = Export()
    ex.sleep = [night("A", "2026-10-01 17:00:00", "2026-10-01 22:00:00", tz=300),
                night("B", "2026-10-01 23:00:00", "2026-10-02 03:30:00", tz=-240)]
    sessions, _ = wd.derive_sleep(ex.sleep, [])
    assert {s.wake_date for s in sessions} == {D(2026, 10, 1)} and all(s.is_main for s in sessions)
    assert wd.derive_days(ex, sessions) == {D(2026, 10, 1): {"sleep_total_min": 300 + 270}}


def test_nap_alone_is_never_main():
    nap = night("nap", "2026-10-02 09:00:00", "2026-10-02 09:40:00", sleep_type="3")
    (s,), _ = wd.derive_sleep([nap], [])
    assert not s.is_main


def test_orphan_stages_ignored_and_bad_session_dropped():
    rec = night("n1", "2026-10-01 20:00:00", "2026-10-02 02:00:00")
    bad = night("bad", "2026-10-02 02:00:00", "2026-10-02 02:00:00")  # zero length
    stages = [StageRec("o1", "ghost", t("2026-10-01 20:00:00"), t("2026-10-01 21:00:00"), "deep"),
              StageRec("s1", "n1", t("2026-10-01 20:00:00"), t("2026-10-01 21:00:00"), "deep")]
    sessions, by_session = wd.derive_sleep([rec, bad], stages)
    assert [s.external_id for s in sessions] == ["n1"]
    assert set(by_session) == {"n1"} and sessions[0].deep_min == 60


# ---------------------------------------------------------------- derive_days

def _night_export() -> tuple[Export, list[SleepIn]]:
    """Main night 2026-10-01 18:00 -> 2026-10-02 02:00 UTC (+0500, wake 2026-10-02), a nap at 09:00-09:40 UTC."""
    ex = Export()
    ex.sleep = [night("main", "2026-10-01 18:00:00", "2026-10-02 02:00:00", eff=92.0),
                night("nap", "2026-10-02 09:00:00", "2026-10-02 09:40:00", sleep_type="3")]
    ex.stages = [StageRec("a", "main", t("2026-10-01 18:00:00"), t("2026-10-01 18:20:00"), "awake"),
                 StageRec("l", "main", t("2026-10-01 18:20:00"), t("2026-10-01 22:00:00"), "light"),
                 StageRec("d", "main", t("2026-10-01 22:00:00"), t("2026-10-01 23:30:00"), "deep"),
                 StageRec("r", "main", t("2026-10-01 23:30:00"), t("2026-10-02 02:00:00"), "rem")]
    tz = 300
    ex.hr = (hr_run("2026-10-01 20:00:00", [52.4] * 30 + [49.6] * 30)  # in the main window
             + hr_run("2026-10-02 09:05:00", [41.0] * 30)  # during the nap
             + hr_run("2026-10-01 11:00:00", [38.0] * 30))  # daytime
    ex.hrv = [BinRec(t("2026-10-01 19:00:00"), t("2026-10-01 19:05:00"), tz, 40.04, 30.0),
              BinRec(t("2026-10-01 21:00:00"), t("2026-10-01 21:05:00"), tz, 50.0, 41.07),
              BinRec(t("2026-10-02 09:05:00"), t("2026-10-02 09:10:00"), tz, 99.0, 99.0)]  # nap: excluded
    ex.resp = [BinRec(t("2026-10-01 19:00:00"), t("2026-10-01 19:10:00"), tz, 14.0),
               BinRec(t("2026-10-01 20:00:00"), t("2026-10-01 20:10:00"), tz, 15.1)]
    ex.skin = [BinRec(t("2026-10-01 19:00:00"), t("2026-10-01 19:10:00"), tz, 33.555, None),
               BinRec(t("2026-10-01 20:00:00"), t("2026-10-01 20:10:00"), tz, 33.7, None)]
    ex.spo2 = [SpO2Rec(t("2026-10-01 19:00:00"), tz, 95.0, 91.0), SpO2Rec(t("2026-10-01 21:00:00"), tz, 97.0, None),
               SpO2Rec(t("2026-10-01 10:00:00"), tz, 80.0, 70.0)]  # daytime
    ex.steps = [StepsDay(D(2026, 10, 2), 8123, 6012.4, 310.6)]
    ex.stress = [StressRec(t("2026-10-02 06:00:00"), tz, 30), StressRec(t("2026-10-02 12:00:00"), tz, 45),
                 StressRec(t("2026-10-02 20:00:00"), tz, 99)]  # 01:00 local on 10-03
    sessions, _ = wd.derive_sleep(ex.sleep, ex.stages)
    return ex, sessions


def test_nightly_metrics_from_main_sleep_only():
    ex, sessions = _night_export()
    days = wd.derive_days(ex, sessions)
    d = days[D(2026, 10, 2)]
    assert d["resting_hr"] == 50  # lowest 30-min mean inside the main window (49.6), not the nap 41 or daytime 38
    assert d["hrv_sdnn"] == 45.0 and d["hrv_rmssd"] == 35.5  # mean of the two in-window bins, nap bin excluded
    assert d["respiratory_rate"] == 14.6
    assert d["skin_temp_c"] == 33.63  # 2 dp
    assert "skin_temp_delta" not in d  # no row baseline and no history
    assert d["spo2_avg"] == 96.0 and d["spo2_min"] == 91.0
    assert d["sleep_awake_min"] == 20 and d["sleep_light_min"] == 220 and d["sleep_deep_min"] == 90
    assert d["sleep_rem_min"] == 150 and d["sleep_total_min"] == 460  # asleep = light + deep + rem
    assert d["sleep_efficiency"] == 92.0
    assert d["steps"] == 8123 and d["distance_m"] == 6012 and d["active_kcal"] == 311
    assert d["stress_avg"] == 37.5
    assert days[D(2026, 10, 3)] == {"stress_avg": 99.0}


def test_resting_hr_only_from_main_window():
    ex, sessions = _night_export()
    ex.hr = [h for h in ex.hr if not (49 < h.hr < 53)]  # only the nap and daytime readings remain
    days = wd.derive_days(ex, sessions)
    assert "resting_hr" not in days[D(2026, 10, 2)]


def _hr_night(hr: list[HrRec]) -> dict[str, float]:
    ex = Export()
    ex.sleep = [night("m", "2026-10-01 18:00:00", "2026-10-02 02:00:00")]
    ex.hr = hr
    return wd.derive_days(ex, wd.derive_sleep(ex.sleep, [])[0])[D(2026, 10, 2)]


def test_single_low_artefact_is_not_resting_hr():
    values = [55.0] * 30
    values[15] = 35.0
    d = _hr_night(hr_run("2026-10-01 19:00:00", values))
    # the lowest window with >= 20 min covered: readings 10..29 (20 min) incl. the 35: (35 + 19 * 55) / 20 = 54.0
    assert d["resting_hr"] == 54


def test_short_low_stretch_at_the_end_of_the_night_is_not_resting_hr():
    # review probe: 7 h at 56 with the last 3 min at 49; truncated windows near the end must not count
    ex = Export()
    ex.sleep = [night("m", "2026-10-01 19:00:00", "2026-10-02 02:00:00")]
    ex.hr = hr_run("2026-10-01 19:00:00", [56.0] * 417 + [49.0] * 3)
    d = wd.derive_days(ex, wd.derive_sleep(ex.sleep, [])[0])[D(2026, 10, 2)]
    assert abs(d["resting_hr"] - 56) <= 1  # lowest full window: (17 * 56 + 3 * 49) / 20 = 54.95 -> 55


def test_sustained_30_min_low_stretch_at_the_end_is_resting_hr():
    ex = Export()
    ex.sleep = [night("m", "2026-10-01 19:00:00", "2026-10-02 02:00:00")]
    ex.hr = hr_run("2026-10-01 19:00:00", [56.0] * 390 + [49.0] * 30)
    assert wd.derive_days(ex, wd.derive_sleep(ex.sleep, [])[0])[D(2026, 10, 2)]["resting_hr"] == 49


def test_window_needs_twenty_minutes_covered():
    # five 1-minute readings 5 min apart: enough readings, only 5 min covered
    assert "resting_hr" not in _hr_night(hr_run("2026-10-01 19:00:00", [50.0] * 5, every_min=5))


def test_sustained_low_stretch_is_resting_hr():
    d = _hr_night(hr_run("2026-10-01 19:00:00", [55.0] * 30 + [45.0] * 30 + [55.0] * 30))
    assert d["resting_hr"] == 45


def test_resting_hr_is_time_weighted():
    # a 20-min reading at 48 and two 1-min readings at 60 in one window: weighted (48*20 + 60 + 60) / 22 = 49.1
    s = t("2026-10-01 19:00:00")
    hr = [HrRec(s, s + dt.timedelta(minutes=20), 300, 48.0, None),
          HrRec(s + dt.timedelta(minutes=21), s + dt.timedelta(minutes=22), 300, 60.0, None),
          HrRec(s + dt.timedelta(minutes=23), s + dt.timedelta(minutes=24), 300, 60.0, None)]
    assert _hr_night(hr)["resting_hr"] == 49


def test_resting_hr_needs_three_readings_in_a_window():
    d = _hr_night(hr_run("2026-10-01 19:00:00", [50.0, 50.0], every_min=10)
                  + hr_run("2026-10-01 21:00:00", [50.0, 50.0], every_min=10))
    assert "resting_hr" not in d


# ---------------------------------------------------------------- split nights

def _split(second_start: str, second_end: str, sleep_type="-1"):
    """Part A 17:00-20:00 UTC (22:00-01:00 local, wakes 2026-10-02) with stages and readings; part B as given."""
    ex = Export()
    ex.sleep = [night("A", "2026-10-01 17:00:00", "2026-10-01 20:00:00", eff=90.0),
                night("B", second_start, second_end, eff=80.0, sleep_type=sleep_type)]
    b0, b1 = t(second_start), t(second_end)
    ex.stages = [StageRec("a1", "A", t("2026-10-01 17:00:00"), t("2026-10-01 18:00:00"), "light"),
                 StageRec("a2", "A", t("2026-10-01 18:00:00"), t("2026-10-01 19:30:00"), "deep"),
                 StageRec("a3", "A", t("2026-10-01 19:30:00"), t("2026-10-01 20:00:00"), "awake"),
                 StageRec("b1", "B", b0, b0 + dt.timedelta(minutes=60), "rem"),
                 StageRec("b2", "B", b0 + dt.timedelta(minutes=60), b1, "light")]
    ex.hrv = [BinRec(t("2026-10-01 18:00:00"), t("2026-10-01 18:05:00"), 300, 40.0, 30.0),
              BinRec(b0 + dt.timedelta(minutes=30), b0 + dt.timedelta(minutes=35), 300, 60.0, 50.0)]
    ex.hr = hr_run("2026-10-01 18:00:00", [56.0] * 30) + hr_run(second_start, [48.0] * 30)
    sessions, _ = wd.derive_sleep(ex.sleep, ex.stages)
    return ex, sessions


def test_split_night_within_gap_is_merged():
    ex, sessions = _split("2026-10-01 21:30:00", "2026-10-01 23:30:00")  # 90 min after A, 3 h + 2 h
    s = by_id(sessions)
    assert s["A"].is_main and s["B"].is_main
    d = wd.derive_days(ex, sessions)[D(2026, 10, 2)]
    assert d["sleep_light_min"] == 60 + 60 and d["sleep_deep_min"] == 90 and d["sleep_rem_min"] == 60
    assert d["sleep_awake_min"] == 30 and d["sleep_total_min"] == 270
    assert d["hrv_sdnn"] == 50.0 and d["hrv_rmssd"] == 40.0  # both windows
    assert d["resting_hr"] == 48  # the lower stretch is in part B
    assert d["sleep_efficiency"] == round((90 * 180 + 80 * 120) / 300, 1)  # duration-weighted


def test_split_part_beyond_gap_is_not_merged():
    ex, sessions = _split("2026-10-02 00:00:00", "2026-10-02 02:00:00")  # 4 h after A, same wake date
    s = by_id(sessions)
    assert s["A"].is_main and not s["B"].is_main
    d = wd.derive_days(ex, sessions)[D(2026, 10, 2)]
    assert d["sleep_total_min"] == 150 and d["hrv_sdnn"] == 40.0 and d["resting_hr"] == 56


def test_split_parts_chain():
    ex = Export()
    ex.sleep = [night("A", "2026-10-01 17:00:00", "2026-10-01 20:00:00"),  # 3 h
                night("B", "2026-10-01 22:00:00", "2026-10-01 23:00:00"),  # 2 h after A
                night("C", "2026-10-02 01:30:00", "2026-10-02 02:00:00")]  # 2.5 h after B, 5.5 h after A
    s = by_id(wd.derive_sleep(ex.sleep, [])[0])
    assert s["A"].is_main and s["B"].is_main and s["C"].is_main


def test_nap_is_never_merged_and_duplicate_still_excluded():
    _, sessions = _split("2026-10-01 20:30:00", "2026-10-01 21:00:00", sleep_type="3")
    assert not by_id(sessions)["B"].is_main
    dup = night("dup", "2026-10-01 17:10:00", "2026-10-01 19:50:00", device="phone")
    a = night("A", "2026-10-01 17:00:00", "2026-10-01 20:00:00")
    s = by_id(wd.derive_sleep([a, dup], [])[0])
    assert s["A"].is_main and not s["dup"].is_main


def test_no_main_sleep_no_night_metrics_but_steps_present():
    ex, _ = _night_export()
    nap_only = [s for s in wd.derive_sleep(ex.sleep, ex.stages)[0] if s.external_id == "nap"]
    days = wd.derive_days(ex, nap_only)
    d = days[D(2026, 10, 2)]
    assert d["steps"] == 8123
    night_fields = {"resting_hr", "hrv_sdnn", "hrv_rmssd", "respiratory_rate", "skin_temp_c", "skin_temp_delta",
                    "spo2_avg", "spo2_min", "sleep_total_min", "sleep_deep_min", "sleep_rem_min", "sleep_light_min",
                    "sleep_awake_min", "sleep_efficiency"}
    assert not night_fields & set(d)


def test_main_sleep_without_stages_uses_duration_and_no_stage_fields():
    ex = Export()
    ex.sleep = [night("m", "2026-10-01 18:00:00", "2026-10-02 02:00:00")]
    sessions, _ = wd.derive_sleep(ex.sleep, [])
    d = wd.derive_days(ex, sessions)[D(2026, 10, 2)]
    assert d == {"sleep_total_min": 480}


def test_efficiency_computed_from_stages_when_samsung_has_none():
    ex, _ = _night_export()
    ex.sleep = [night("main", "2026-10-01 18:00:00", "2026-10-02 02:00:00", eff=None)]
    sessions, _ = wd.derive_sleep(ex.sleep, ex.stages)
    d = wd.derive_days(ex, sessions)[D(2026, 10, 2)]
    assert d["sleep_efficiency"] == round(460 / 480 * 100, 1)


def _skin_nights(n: int, start: D, temp=34.0, baseline=None) -> Export:
    ex = Export()
    for i in range(n):
        wake = start + dt.timedelta(days=i)
        s = dt.datetime.combine(wake - dt.timedelta(days=1), dt.time(18), UTC)  # 23:00 local the evening before
        ex.sleep.append(SleepRec(f"n{i}", s, s + dt.timedelta(hours=8), 300, "-1", None, "w"))
        ex.skin.append(BinRec(s + dt.timedelta(hours=1), s + dt.timedelta(hours=1, minutes=10), 300,
                              temp + (i % 3) * 0.1, baseline))
    return ex


def test_skin_delta_uses_row_baseline_when_present():
    ex = _skin_nights(1, D(2026, 10, 2), temp=34.0, baseline=33.5)
    sessions, _ = wd.derive_sleep(ex.sleep, [])
    d = wd.derive_days(ex, sessions)[D(2026, 10, 2)]
    assert d["skin_temp_c"] == 34.0 and d["skin_temp_delta"] == 0.5


def test_skin_delta_from_30_night_median_after_seven_nights_none_before():
    ex = _skin_nights(10, D(2026, 10, 1))  # temps cycle 34.0, 34.1, 34.2
    sessions, _ = wd.derive_sleep(ex.sleep, [])
    days = wd.derive_days(ex, sessions)
    dates = sorted(days)
    for d in dates[:7]:  # nights 1..7 have 0..6 previous nights
        assert "skin_temp_delta" not in days[d]
    eighth = days[dates[7]]  # 7 previous nights: 34.0 34.1 34.2 34.0 34.1 34.2 34.0 -> median 34.1
    assert eighth["skin_temp_c"] == 34.1 and eighth["skin_temp_delta"] == 0.0
    ninth = days[dates[8]]  # i=8 -> 34.2; previous 8 nights median 34.1
    assert ninth["skin_temp_delta"] == 0.1


def test_skin_median_window_is_the_previous_30_days():
    ex = _skin_nights(8, D(2026, 1, 1))  # an old block of history
    later = _skin_nights(1, D(2026, 10, 2))
    ex.sleep.append(SleepRec("late", later.sleep[0].start_utc, later.sleep[0].end_utc, 300, "-1", None, "w"))
    ex.skin += later.skin
    sessions, _ = wd.derive_sleep(ex.sleep, [])
    days = wd.derive_days(ex, sessions)
    assert "skin_temp_delta" not in days[D(2026, 10, 2)]


def test_end_to_end_with_synthetic_export(tmp_path):
    ex = se.read_export(build_export(tmp_path / "x.zip"))
    sessions, stages = wd.derive_sleep(ex.sleep, ex.stages)
    days = wd.derive_days(ex, sessions)
    main = [s for s in sessions if s.is_main]
    assert len(main) == 1 and main[0].wake_date == D(2026, 10, 2)
    assert days[D(2026, 10, 2)]["sleep_deep_min"] == 90
    assert "hrv_sdnn" in days[D(2026, 10, 2)]
    assert days[D(2026, 10, 2)]["resting_hr"] == 50  # from the per-minute heart-rate bins (mean 49.8)


def test_partially_overlapping_parts_count_overlap_once():
    # A 17:00-22:00 (300 min), B 21:30-00:00 (150 min): 30 min overlap = 20 % of B, not a duplicate
    ex = Export()
    ex.sleep = [night("A", "2026-10-01 17:00:00", "2026-10-01 22:00:00"),
                night("B", "2026-10-01 21:30:00", "2026-10-02 00:00:00")]
    ex.stages = [StageRec("a", "A", t("2026-10-01 17:00:00"), t("2026-10-01 22:00:00"), "light"),
                 StageRec("b", "B", t("2026-10-01 21:30:00"), t("2026-10-02 00:00:00"), "deep")]
    sessions, _ = wd.derive_sleep(ex.sleep, ex.stages)
    assert all(s.is_main for s in sessions)
    d = wd.derive_days(ex, sessions)[D(2026, 10, 2)]
    assert d["sleep_total_min"] == 420  # union length, not 450
    assert d["sleep_light_min"] == 300 and d["sleep_deep_min"] == 120  # the earlier-starting stage keeps the overlap
    assert d["sleep_light_min"] + d["sleep_deep_min"] + d.get("sleep_rem_min", 0) + d.get("sleep_awake_min", 0) <= 420


def test_overlapping_unstaged_parts_total_is_union_length():
    ex = Export()
    ex.sleep = [night("A", "2026-10-01 17:00:00", "2026-10-01 22:00:00"),
                night("B", "2026-10-01 21:30:00", "2026-10-02 00:00:00")]
    d = wd.derive_days(ex, wd.derive_sleep(ex.sleep, [])[0])[D(2026, 10, 2)]
    assert d == {"sleep_total_min": 420}


# ---------------------------------------------------------------- performance

def test_derive_days_is_fast_on_large_input():
    ex = Export()
    tz = 300
    start = dt.datetime(2026, 1, 1, 18, tzinfo=UTC)
    for i in range(200):
        s = start + dt.timedelta(days=i)
        ex.sleep.append(SleepRec(f"n{i}", s, s + dt.timedelta(hours=8), tz, "-1", 90.0, "w"))
        for k in range(600):  # 600 bins per type per night, spread over the whole day (in and out of sleep)
            b = s + dt.timedelta(seconds=k * 144)
            ex.hrv.append(BinRec(b, b + dt.timedelta(minutes=1), tz, 40.0 + k % 7, 30.0))
            ex.skin.append(BinRec(b, b + dt.timedelta(minutes=1), tz, 34.0, None))
            ex.resp.append(BinRec(b, b + dt.timedelta(minutes=1), tz, 14.0))
            ex.hr.append(HrRec(b, b, tz, 50.0 + k % 9, None))
    ex.hrv.reverse()  # unsorted input
    t0 = time.process_time()  # CPU time: not skewed by machine load
    sessions, _ = wd.derive_sleep(ex.sleep, ex.stages)
    days = wd.derive_days(ex, sessions)
    elapsed = time.process_time() - t0
    assert len(days) == 200 and all("hrv_sdnn" in d for d in days.values())
    assert elapsed < 3.0, elapsed


# ---------------------------------------------------------------- body and workouts

def test_derive_body_drops_non_positive_and_keeps_last_per_day():
    ex = Export()
    tz = 300
    ex.body = [BodyRec(t("2026-10-02 03:00:00"), tz, "weight", 80.5),
               BodyRec(t("2026-10-02 08:00:00"), tz, "weight", 80.1),  # later the same local day: wins
               BodyRec(t("2026-10-02 03:00:00"), tz, "body_fat_pct", 0.0),
               BodyRec(t("2026-10-03 03:00:00"), tz, "muscle_kg", -1.0),
               BodyRec(t("2026-10-03 03:00:00"), tz, "visceral_fat", 9.0)]
    assert wd.derive_body(ex) == {D(2026, 10, 2): {"weight": 80.1}, D(2026, 10, 3): {"visceral_fat": 9.0}}


def test_parser_zero_weigh_in_does_not_hide_an_earlier_value(tmp_path):
    tables = tables_copy()
    row = dict(tables["weight"].rows[0])
    tables["weight"].rows.append({**row, "start_time": "2026-10-02 06:00:00.000", "datauuid": "wt-2", "weight": "0",
                                  "body_fat": "", "skeletal_muscle_mass": "", "basal_metabolic_rate": "",
                                  "vfa_level": "", "height": ""})
    ex = se.read_export(build_export(tmp_path / "x.zip", tables))
    assert wd.derive_body(ex)[D(2026, 10, 2)]["weight"] == 80.5


def test_derive_workouts_maps_and_drops_bad_rows():
    ex = Export()
    ex.workouts = [
        WorkoutRec("w1", t("2026-10-02 20:00:00"), t("2026-10-02 20:45:30"), 300, 1002, 45.5, 410.26, 6012.7, 131.6,
                   160.2, "watch"),  # 01:00 local next day
        WorkoutRec("w2", t("2026-10-02 10:00:00"), t("2026-10-02 09:00:00"), 300, 1001, 30.0, None, None, None, None,
                   ""),  # end before start
        WorkoutRec("w3", t("2026-10-02 10:00:00"), t("2026-10-02 10:00:00"), 300, 1001, 0.0, None, None, None, None,
                   ""),  # zero duration
    ]
    items, dropped = wd.derive_workouts(ex)
    assert dropped == 2
    (w,) = items
    assert w == WorkoutIn("w1", t("2026-10-02 20:00:00"), t("2026-10-02 20:45:30"), 300, D(2026, 10, 3), 1002, 46,
                          410, 6013, 132, 160, "watch")
