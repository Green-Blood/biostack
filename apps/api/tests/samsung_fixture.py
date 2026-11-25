"""Builds a small synthetic Samsung Health export ZIP with the same structure as a real one (invented values only).

Layout: `Samsung Health/samsunghealth_<user>_<stamp>/com.samsung.(health|shealth).<type>.<stamp>.csv` with line 1 =
metadata, line 2 = header (some columns fully qualified, some bare), rows with a trailing comma, and binning detail
files at `jsons/com.samsung.health.<type>/<x>/<datauuid>.binning_data.json`.
"""
import copy
import dataclasses
import io
import json
import zipfile
from pathlib import Path

STAMP = "20261101120000"
ROOT = f"Samsung Health/samsunghealth_synthetic_{STAMP}"

HR_DETAIL_ID = "eeeeeeee-0000-4000-8000-000000000001"
HR_MISSING_ID = "ffffffff-0000-4000-8000-000000000001"
HR_SUFFIX = ".com.samsung.health.heart_rate.binning_data.json"  # as the real export names heart-rate detail files
# Where each type's detail files live and how they are named after the datauuid (default: health prefix, no infix).
JSON_LAYOUT = {"tracker.heart_rate": ("com.samsung.shealth", ".com.samsung.health.heart_rate")}

# Stage codes as Samsung writes them.
AWAKE, LIGHT, DEEP, REM = "40001", "40002", "40003", "40004"


def _ms(text: str) -> int:
    import datetime as dt
    return int(dt.datetime.fromisoformat(text).replace(tzinfo=dt.UTC).timestamp() * 1000)


@dataclasses.dataclass
class Table:
    prefix: str  # "com.samsung.health" or "com.samsung.shealth"
    qualified_prefix: str  # what fully-qualified header names start with, e.g. "com.samsung.health.heart_rate"
    qualified: list[str]  # columns written fully qualified
    bare: list[str]  # columns written without the prefix
    rows: list[dict]


def default_tables() -> dict[str, Table]:
    """Every table keyed by its type name as it appears in the file name."""
    sleep_id = "aaaaaaaa-0000-4000-8000-000000000001"
    nap_id = "aaaaaaaa-0000-4000-8000-000000000002"
    common = ["start_time", "end_time", "time_offset", "datauuid", "deviceuuid", "create_time", "update_time",
              "pkg_name", "custom", "comment"]
    return {
        "sleep": Table("com.samsung.shealth", "com.samsung.health.sleep", common,
                       ["efficiency", "sleep_type", "sleep_score", "extra_data", "original_efficiency"], [
            # 22:00 UTC -> 03:00 local (+0500) start, 05:00 UTC -> 10:00 local: wake-up on 2026-10-02 local
            dict(start_time="2026-10-01 22:00:00.000", end_time="2026-10-02 05:00:00.000", time_offset="UTC+0500",
                 datauuid=sleep_id, deviceuuid="dev-watch", efficiency="91.5", sleep_type="-1", sleep_score="80"),
            dict(start_time="2026-10-02 09:00:00.000", end_time="2026-10-02 09:40:00.000", time_offset="UTC+0500",
                 datauuid=nap_id, deviceuuid="dev-phone", efficiency="", sleep_type="3"),
        ]),
        "sleep_stage": Table("com.samsung.health", "com.samsung.health.sleep_stage", common, ["sleep_id", "stage"], [
            dict(start_time="2026-10-01 22:00:00.000", end_time="2026-10-01 22:10:00.000", time_offset="UTC+0500",
                 datauuid="st-1", sleep_id=sleep_id, stage=AWAKE),
            dict(start_time="2026-10-01 22:10:00.000", end_time="2026-10-02 00:00:00.000", time_offset="UTC+0500",
                 datauuid="st-2", sleep_id=sleep_id, stage=LIGHT),
            dict(start_time="2026-10-02 00:00:00.000", end_time="2026-10-02 01:30:00.000", time_offset="UTC+0500",
                 datauuid="st-3", sleep_id=sleep_id, stage=DEEP),
            dict(start_time="2026-10-02 01:30:00.000", end_time="2026-10-02 05:00:00.000", time_offset="UTC+0500",
                 datauuid="st-4", sleep_id=sleep_id, stage=REM),
        ]),
        "tracker.heart_rate": Table("com.samsung.shealth", "com.samsung.health.heart_rate", common,
                                    ["heart_rate", "min", "max", "binning_data", "source", "tag_id"], [
            dict(start_time="2026-10-02 01:00:00.000", end_time="2026-10-02 01:00:59.000", time_offset="UTC+0500",
                 datauuid="hr-1", heart_rate="52", min="50", max="55", binning_data=""),
            dict(start_time="2026-10-02 20:30:00.000", end_time="2026-10-02 20:31:00.000", time_offset="UTC+0500",
                 datauuid="hr-2", heart_rate="61", min="", max="64", binning_data=""),
            # an hourly row with per-minute detail (the detail replaces the row) inside the main night
            dict(start_time="2026-10-02 00:00:00.000", end_time="2026-10-02 00:59:59.000", time_offset="UTC+0500",
                 datauuid=HR_DETAIL_ID, heart_rate="58", min="47", max="70", binning_data=f"{HR_DETAIL_ID}{HR_SUFFIX}"),
            # an hourly row whose detail file is missing: the row itself is kept
            dict(start_time="2026-10-02 10:00:00.000", end_time="2026-10-02 10:59:59.000", time_offset="UTC+0500",
                 datauuid=HR_MISSING_ID, heart_rate="77", min="70", max="90",
                 binning_data=f"{HR_MISSING_ID}{HR_SUFFIX}"),
        ]),
        "hrv": Table("com.samsung.health", "com.samsung.health.hrv", common, ["binning_data"], [
            dict(start_time="2026-10-01 22:00:00.000", end_time="2026-10-02 05:00:00.000", time_offset="UTC+0500",
                 datauuid="bbbbbbbb-0000-4000-8000-000000000001",
                 binning_data="bbbbbbbb-0000-4000-8000-000000000001.bin"),
        ]),
        "skin_temperature": Table("com.samsung.health", "com.samsung.health.skin_temperature", common,
                                  ["temperature", "min", "max", "baseline", "binning_data", "stat_n"], [
            dict(start_time="2026-10-01 22:00:00.000", end_time="2026-10-02 05:00:00.000", time_offset="UTC+0500",
                 datauuid="cccccccc-0000-4000-8000-000000000001", temperature="33.9", baseline="33.6",
                 binning_data="cccccccc-0000-4000-8000-000000000001.bin"),
        ]),
        "respiratory_rate": Table("com.samsung.health", "com.samsung.health.respiratory_rate", common,
                                  ["average", "lower_limit", "upper_limit", "binning_data", "is_outlier"], [
            dict(start_time="2026-10-01 22:00:00.000", end_time="2026-10-02 05:00:00.000", time_offset="UTC+0500",
                 datauuid="dddddddd-0000-4000-8000-000000000001", average="14.5",
                 binning_data="dddddddd-0000-4000-8000-000000000001.bin"),
            # no detail file: falls back to the row's average
            dict(start_time="2026-10-02 22:00:00.000", end_time="2026-10-03 05:00:00.000", time_offset="UTC+0500",
                 datauuid="dddddddd-0000-4000-8000-000000000002", average="15.0", binning_data=""),
        ]),
        "tracker.oxygen_saturation": Table("com.samsung.shealth", "com.samsung.health.oxygen_saturation", common,
                                           ["spo2", "min", "max", "low_duration", "heart_rate", "binning"], [
            dict(start_time="2026-10-02 02:00:00.000", end_time="2026-10-02 02:00:30.000", time_offset="UTC+0500",
                 datauuid="ox-1", spo2="96", min="92", max="99"),
        ]),
        "tracker.pedometer_day_summary": Table("com.samsung.shealth", "com.samsung.shealth.tracker.pedometer_day_summary",
                                               ["datauuid", "deviceuuid", "create_time", "pkg_name"],
                                               ["day_time", "step_count", "distance", "calorie", "binning_data",
                                                "source_package_name"], [
            dict(day_time="2026-10-02 00:00:00.000", datauuid="pd-1", step_count="8000", distance="5600.5",
                 calorie="310.2", binning_data="pd-1.bin"),
            # a second device's summary for the same day: smaller, dropped
            dict(day_time="2026-10-02 00:00:00.000", datauuid="pd-2", step_count="1200", distance="800",
                 calorie="40", binning_data=""),
        ]),
        "step_daily_trend": Table("com.samsung.shealth", "com.samsung.shealth.step_daily_trend",
                                  ["datauuid", "deviceuuid", "create_time", "pkg_name"],
                                  ["day_time", "count", "distance", "calorie", "speed", "source_type", "binning_data"], [
            # same day as the pedometer summary: deduped to the larger count
            dict(day_time="2026-10-02 00:00:00.000", datauuid="tr-1", count="7900", distance="5500",
                 calorie="300", source_type="-2"),
            # a day the pedometer summary lacks: filled from the trend
            dict(day_time="2026-10-03 00:00:00.000", datauuid="tr-2", count="4321", distance="3000",
                 calorie="150", source_type="-2"),
        ]),
        "stress": Table("com.samsung.shealth", "com.samsung.shealth.stress", common,
                        ["score", "min", "max", "algorithm", "binning_data", "tag_id"], [
            # 20:30 UTC at +0500 is 01:30 the next local day
            dict(start_time="2026-10-02 20:30:00.000", end_time="2026-10-02 20:31:00.000", time_offset="UTC+0500",
                 datauuid="sr-1", score="35"),
            dict(start_time="2026-10-02 10:00:00.000", end_time="2026-10-02 10:01:00.000", time_offset="UTC-0400",
                 datauuid="sr-2", score="22"),
        ]),
        "exercise": Table("com.samsung.shealth", "com.samsung.health.exercise", common,
                          ["exercise_type", "duration", "calorie", "total_calorie", "distance", "mean_heart_rate",
                           "max_heart_rate", "min_heart_rate", "live_data", "title"], [
            dict(start_time="2026-10-02 12:00:00.000", end_time="2026-10-02 12:45:00.000", time_offset="UTC+0500",
                 datauuid="ex-1", deviceuuid="dev-watch", exercise_type="1001", duration="2700000", calorie="250.5",
                 distance="4100", mean_heart_rate="118", max_heart_rate="141",
                 live_data='[{"heart_rate": 1, "note": "a, quoted \\"field\\" with commas"}]'),
            dict(start_time="2026-10-03 06:00:00.000", end_time="2026-10-03 06:30:00.000", time_offset="UTC+0500",
                 datauuid="ex-2", exercise_type="0", duration="", calorie="", total_calorie="90", distance=""),
        ]),
        "weight": Table("com.samsung.health", "com.samsung.health.weight", common,
                        ["weight", "body_fat", "skeletal_muscle_mass", "total_body_water", "basal_metabolic_rate",
                         "height", "vfa_level", "body_fat_mass", "muscle_mass"], [
            dict(start_time="2026-10-02 03:00:00.000", time_offset="UTC+0500", datauuid="wt-1", weight="80.5",
                 body_fat="20.1", skeletal_muscle_mass="35.2", muscle_mass="52.0", total_body_water="45.0", basal_metabolic_rate="1750",
                 height="181", vfa_level="9"),
        ]),
        # a type the importer does not read
        "food_intake": Table("com.samsung.health", "com.samsung.health.food_intake", common, ["calorie"], [
            dict(start_time="2026-10-02 03:00:00.000", time_offset="UTC+0500", datauuid="fi-1", calorie="500"),
        ]),
    }


def default_jsons() -> dict[tuple[str, str], list[dict]]:
    """Binning detail files keyed by (type, datauuid)."""
    return {
        ("hrv", "bbbbbbbb-0000-4000-8000-000000000001"): [
            dict(start_time=_ms("2026-10-01 22:00:00"), end_time=_ms("2026-10-01 22:05:00"), sdnn=41.2, rmssd=35.0),
            dict(start_time=_ms("2026-10-01 23:00:00"), end_time=_ms("2026-10-01 23:05:00"), sdnn=45.8, rmssd=38.4),
        ],
        ("skin_temperature", "cccccccc-0000-4000-8000-000000000001"): [
            dict(start_time=_ms("2026-10-01 22:00:00"), end_time=_ms("2026-10-01 22:10:00"), mean=33.8, min=33.5,
                 max=34.0),
        ],
        ("tracker.heart_rate", HR_DETAIL_ID): [
            dict(start_time=_ms(f"2026-10-02 00:{i:02d}:00"), end_time=_ms(f"2026-10-02 00:{i:02d}:59"),
                 heart_rate=v, heart_rate_min=v - 2, heart_rate_max=v + 3)
            for i, v in enumerate([49.0, 50.0, 51.0, 50.0, 49.0] * 5)
        ] + [dict(start_time=_ms("2026-10-02 00:30:00"), end_time=_ms("2026-10-02 00:30:59"), heart_rate=0.0,
                  heart_rate_min=0.0, heart_rate_max=0.0)],  # a zero bin: junk
        ("respiratory_rate", "dddddddd-0000-4000-8000-000000000001"): [
            dict(start_time=_ms("2026-10-01 22:00:00"), end_time=_ms("2026-10-01 22:10:00"), respiratory_rate=14.2),
            dict(start_time=_ms("2026-10-01 22:10:00"), end_time=_ms("2026-10-01 22:20:00"), respiratory_rate=14.8),
        ],
    }


def _csv_text(type_name: str, table: Table) -> str:
    out = io.StringIO()
    out.write(f"{table.prefix}.{type_name},7013005,{len(table.qualified) + len(table.bare)}\n")
    header = [f"{table.qualified_prefix}.{c}" for c in table.qualified] + list(table.bare)
    out.write(",".join(header) + ",\n")
    order = table.qualified + table.bare
    for row in table.rows:
        cells = []
        for col in order:
            v = str(row.get(col, ""))
            if any(ch in v for ch in ',"\n'):
                v = '"' + v.replace('"', '""') + '"'
            cells.append(v)
        out.write(",".join(cells) + ",\n")
    return out.getvalue()


def build_export(path: Path, tables: dict[str, Table] | None = None,
                 jsons: dict[tuple[str, str], list[dict]] | None = None) -> Path:
    tables = default_tables() if tables is None else tables
    jsons = default_jsons() if jsons is None else jsons
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for type_name, table in tables.items():
            zf.writestr(f"{ROOT}/{table.prefix}.{type_name}.{STAMP}.csv", _csv_text(type_name, table))
        for (type_name, uuid), items in jsons.items():
            prefix, infix = JSON_LAYOUT.get(type_name, ("com.samsung.health", ""))
            zf.writestr(f"{ROOT}/jsons/{prefix}.{type_name}/{uuid[0]}/{uuid}{infix}.binning_data.json",
                        json.dumps(items))
        # unrelated detail files and media that must be ignored
        zf.writestr(f"{ROOT}/jsons/com.samsung.shealth.exercise/e/ex-1.com.samsung.health.exercise.live_data.json",
                    "[]")
        zf.writestr(f"{ROOT}/files/profile/image.jpg", b"\xff\xd8")
    return path


def tables_copy() -> dict[str, Table]:
    return copy.deepcopy(default_tables())
