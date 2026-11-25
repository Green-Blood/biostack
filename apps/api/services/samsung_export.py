"""Reads a Samsung Health data export (ZIP) into plain records, one member at a time.

The export holds `com.samsung.(health|shealth).<type>.<stamp>.csv` files (line 1 metadata, line 2 header, then rows)
and binning detail files `jsons/com.samsung.health.<type>/<x>/<datauuid>.binning_data.json`. Times in the CSVs are UTC
strings; each row's `time_offset` (`UTC+0500`) gives its local time. Nothing here touches the database: turning records
into days is wearable_derive's job, writing them is wearable_ingest's.

Memory: CSVs are streamed row by row through `csv`, and only one ZIP member is ever open at a time (a binned type's
rows are collected first, then its detail files are read one by one).
"""
import csv
import dataclasses
import datetime as dt
import io
import json
import re
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path

UTC = dt.UTC
STAGES = {"40001": "awake", "40002": "light", "40003": "deep", "40004": "rem"}
BODY_KINDS = {"weight": "weight", "body_fat": "body_fat_pct", "muscle_mass": "muscle_kg",
              "basal_metabolic_rate": "bmr_kcal", "vfa_level": "visceral_fat",
              "skeletal_muscle_mass": "skeletal_muscle_kg", "skeletal_muscle": "skeletal_muscle_pct"}
# not read: total_body_water (unit unclear)

_CSV_NAME = re.compile(r"(?:^|/)com\.samsung\.(?:health|shealth)\.([a-z0-9_.]+?)\.\d{8,}\.csv$")
# `<datauuid>.binning_data.json`, or `<datauuid>.com.samsung.health.heart_rate.binning_data.json` for heart rate
_JSON_NAME = re.compile(
    r"(?:^|/)jsons/com\.samsung\.(?:health|shealth)\.([a-z0-9_.]+)/[^/]+/([^/.]+)[^/]*\.binning_data\.json$")
_OFFSET = re.compile(r"^UTC([+-])(\d{2})(\d{2})$")


# ---------------------------------------------------------------- records

def _local(utc: dt.datetime, tz_min: int) -> dt.date:
    return (utc + dt.timedelta(minutes=tz_min)).date()


@dataclasses.dataclass(frozen=True, slots=True)
class SleepRec:
    uuid: str
    start_utc: dt.datetime
    end_utc: dt.datetime
    tz_min: int
    sleep_type: str
    efficiency: float | None
    device: str

    @property
    def wake_date(self) -> dt.date:
        """A night belongs to the local date it ends on."""
        return _local(self.end_utc, self.tz_min)


@dataclasses.dataclass(frozen=True, slots=True)
class StageRec:
    uuid: str
    sleep_uuid: str
    start_utc: dt.datetime
    end_utc: dt.datetime
    stage: str  # awake | light | deep | rem


@dataclasses.dataclass(frozen=True, slots=True)
class BinRec:
    """One detail bin. HRV: value=sdnn, value2=rmssd. Skin temp: value=mean, value2=the row's baseline. Respiratory:
    value=breaths per minute."""
    start_utc: dt.datetime
    end_utc: dt.datetime
    tz_min: int
    value: float
    value2: float | None = None

    @property
    def local_date(self) -> dt.date:
        return _local(self.start_utc, self.tz_min)


@dataclasses.dataclass(frozen=True, slots=True)
class SpO2Rec:
    start_utc: dt.datetime
    tz_min: int
    spo2: float
    min: float | None

    @property
    def local_date(self) -> dt.date:
        return _local(self.start_utc, self.tz_min)


@dataclasses.dataclass(frozen=True, slots=True)
class HrRec:
    start_utc: dt.datetime
    end_utc: dt.datetime
    tz_min: int
    hr: float
    min: float | None

    @property
    def local_date(self) -> dt.date:
        return _local(self.start_utc, self.tz_min)


@dataclasses.dataclass(frozen=True, slots=True)
class StepsDay:
    local_date: dt.date
    steps: int
    distance_m: float | None
    kcal: float | None


@dataclasses.dataclass(frozen=True, slots=True)
class StressRec:
    start_utc: dt.datetime
    tz_min: int
    score: float

    @property
    def local_date(self) -> dt.date:
        return _local(self.start_utc, self.tz_min)


@dataclasses.dataclass(frozen=True, slots=True)
class WorkoutRec:
    uuid: str
    start_utc: dt.datetime
    end_utc: dt.datetime
    tz_min: int
    type_code: int
    duration_min: float
    kcal: float | None
    distance_m: float | None
    hr_avg: float | None
    hr_max: float | None
    device: str

    @property
    def local_date(self) -> dt.date:
        return _local(self.start_utc, self.tz_min)


@dataclasses.dataclass(frozen=True, slots=True)
class BodyRec:
    start_utc: dt.datetime
    tz_min: int
    kind: str  # a profile measurement kind
    value: float

    @property
    def local_date(self) -> dt.date:
        return _local(self.start_utc, self.tz_min)


@dataclasses.dataclass
class Export:
    sleep: list[SleepRec] = dataclasses.field(default_factory=list)
    stages: list[StageRec] = dataclasses.field(default_factory=list)
    hrv: list[BinRec] = dataclasses.field(default_factory=list)
    skin: list[BinRec] = dataclasses.field(default_factory=list)
    resp: list[BinRec] = dataclasses.field(default_factory=list)
    spo2: list[SpO2Rec] = dataclasses.field(default_factory=list)
    hr: list[HrRec] = dataclasses.field(default_factory=list)
    steps: list[StepsDay] = dataclasses.field(default_factory=list)
    stress: list[StressRec] = dataclasses.field(default_factory=list)
    workouts: list[WorkoutRec] = dataclasses.field(default_factory=list)
    body: list[BodyRec] = dataclasses.field(default_factory=list)
    skipped: dict[str, str] = dataclasses.field(default_factory=dict)  # export type -> reason
    counts: dict[str, int] = dataclasses.field(default_factory=dict)  # record list -> number of records
    junk: dict[str, int] = dataclasses.field(default_factory=dict)  # export type -> unreadable rows dropped
    latest_height_cm: float | None = None  # offered to the owner, never written to the profile automatically


# ---------------------------------------------------------------- value parsing

class Junk(ValueError):
    """A row (or detail item) that cannot be read."""


def parse_offset(text: str) -> int:
    m = _OFFSET.match(text.strip())
    if not m:
        raise ValueError(f"bad time_offset {text!r}")
    minutes = int(m.group(2)) * 60 + int(m.group(3))
    return -minutes if m.group(1) == "-" else minutes


def parse_utc(text: str) -> dt.datetime:
    try:
        return dt.datetime.fromisoformat(text.strip()).replace(tzinfo=UTC)
    except (ValueError, AttributeError) as e:
        raise Junk(str(e)) from None


def _ms(value: object) -> dt.datetime:
    try:
        return dt.datetime.fromtimestamp(float(value) / 1000, UTC)
    except (TypeError, ValueError, OverflowError, OSError) as e:
        raise Junk(str(e)) from None


def _num(text: str | None) -> float:
    try:
        v = float(text)
    except (TypeError, ValueError):
        raise Junk(f"bad number {text!r}") from None
    if v != v or v in (float("inf"), float("-inf")):
        raise Junk("not finite")
    return v


def _opt(text: str | None) -> float | None:
    if text is None or str(text).strip() == "":
        return None
    try:
        return _num(text)
    except Junk:
        return None


def _normalise(column: str) -> str:
    """`com.samsung.health.heart_rate.start_time` -> `start_time`; bare names stay as they are."""
    return column.rsplit(".", 1)[-1] if column.startswith("com.samsung.") else column


# ---------------------------------------------------------------- per-type specs

# Required columns per type. A tuple means "any one of these".
REQUIRED: dict[str, list[str | tuple[str, ...]]] = {
    "sleep": ["start_time", "end_time", "datauuid"],
    "sleep_stage": ["start_time", "end_time", "datauuid", "sleep_id", "stage"],
    "tracker.heart_rate": ["start_time", "datauuid", "heart_rate"],
    "hrv": ["start_time", "datauuid", ("binning_data", "datauuid")],
    "skin_temperature": ["start_time", "datauuid", ("binning_data", "temperature")],
    "respiratory_rate": ["start_time", "datauuid", ("binning_data", "average")],
    "tracker.oxygen_saturation": ["start_time", "datauuid", "spo2"],
    "tracker.pedometer_day_summary": ["day_time", "datauuid", "step_count"],
    "step_daily_trend": ["day_time", "datauuid", "count"],
    "stress": ["start_time", "datauuid", "score"],
    "exercise": ["start_time", "end_time", "datauuid", "exercise_type"],
    "weight": ["start_time", "datauuid", tuple(BODY_KINDS) + ("height",)],
}
BINNED = {"hrv": "hrv", "skin_temperature": "skin", "respiratory_rate": "resp", "tracker.heart_rate": "hr"}


def _missing(columns: set[str], type_name: str) -> list[str]:
    out = []
    for need in REQUIRED[type_name]:
        options = need if isinstance(need, tuple) else (need,)
        if not columns.intersection(options):
            out.append(" or ".join(options))
    return out


# ---------------------------------------------------------------- reading

class _Reader:
    def __init__(self, zf: zipfile.ZipFile, export: Export, default_tz_min: int,
                 progress: Callable[[float, str], None] | None):
        self.zf, self.ex, self.default_tz = zf, export, default_tz_min
        self.progress = progress
        self.done = 0
        self.total = 1
        self.bins: dict[str, dict[str, zipfile.ZipInfo]] = {t: {} for t in BINNED}

    def report(self, stage: str, final: bool = False) -> None:
        if self.progress:
            self.progress(1.0 if final else min(self.done / self.total, 0.99), stage)

    def rows(self, info: zipfile.ZipInfo, type_name: str) -> Iterator[dict[str, str]] | None:
        """Yields rows as {normalised column: text}; None (and a skip reason) if the header lacks a required column.
        The member stays open only while the generator runs."""
        handle = self.zf.open(info)
        try:
            text = io.TextIOWrapper(handle, encoding="utf-8-sig", newline="", errors="replace")
            reader = csv.reader(text)
            next(reader, None)  # metadata line
            header = [_normalise(c.strip()) for c in next(reader, [])]
            missing = _missing({c for c in header if c}, type_name)
        except Exception:
            handle.close()
            raise
        if missing:
            handle.close()
            self.ex.skipped[type_name] = f"missing column(s): {', '.join(missing)}"
            return None
        return self._iter_rows(handle, reader, header, type_name)

    def _iter_rows(self, handle, reader, header, type_name) -> Iterator[dict[str, str]]:
        needed = max(i for i, h in enumerate(header) if h) + 1  # a trailing empty header cell is optional
        try:
            while True:
                try:
                    cells = next(reader)
                except StopIteration:
                    break
                except csv.Error:  # e.g. a field over csv's size limit (left at its default: it is process-wide)
                    self.junk(type_name)
                    continue
                if not cells or all(not c.strip() for c in cells):
                    continue
                if len(cells) < needed:  # truncated row
                    self.junk(type_name)
                    continue
                yield {h: cells[i] for i, h in enumerate(header) if h and i < len(cells)}
        finally:
            handle.close()

    def junk(self, type_name: str, n: int = 1) -> None:
        self.ex.junk[type_name] = self.ex.junk.get(type_name, 0) + n

    def tz(self, row: dict[str, str]) -> int:
        text = (row.get("time_offset") or "").strip()
        if not text:
            return self.default_tz
        try:
            return parse_offset(text)
        except ValueError:
            raise Junk(text) from None

    def read_json(self, info: zipfile.ZipInfo) -> list:
        with self.zf.open(info) as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise Junk("detail is not a list")
        return data


def _each(reader: _Reader, rows: Iterator[dict[str, str]], type_name: str, build: Callable[[dict[str, str]], None]):
    for row in rows:
        try:
            build(row)
        except Junk:
            reader.junk(type_name)


def _read_type(r: _Reader, info: zipfile.ZipInfo, type_name: str, steps: dict[dt.date, StepsDay],
               body: dict[tuple[dt.date, str], BodyRec], heights: list[tuple[dt.datetime, float]]) -> None:
    ex = r.ex
    rows = r.rows(info, type_name)
    if rows is None:
        return

    if type_name == "sleep":
        def build(row):
            ex.sleep.append(SleepRec(row["datauuid"], parse_utc(row["start_time"]), parse_utc(row["end_time"]),
                                     r.tz(row), (row.get("sleep_type") or "").strip(), _opt(row.get("efficiency")),
                                     row.get("deviceuuid", "")))
    elif type_name == "sleep_stage":
        def build(row):
            stage = STAGES.get((row.get("stage") or "").strip())
            if stage is None:
                raise Junk("unknown stage")
            ex.stages.append(StageRec(row["datauuid"], row["sleep_id"], parse_utc(row["start_time"]),
                                      parse_utc(row["end_time"]), stage))
    elif type_name == "tracker.oxygen_saturation":
        def build(row):
            ex.spo2.append(SpO2Rec(parse_utc(row["start_time"]), r.tz(row), _num(row["spo2"]), _opt(row.get("min"))))
    elif type_name == "stress":
        def build(row):
            ex.stress.append(StressRec(parse_utc(row["start_time"]), r.tz(row), _num(row["score"])))
    elif type_name in ("tracker.pedometer_day_summary", "step_daily_trend"):
        count_col = "step_count" if type_name == "tracker.pedometer_day_summary" else "count"

        def build(row):
            day = parse_utc(row["day_time"]).date()  # day_time is the local day at 00:00, written as UTC
            item = StepsDay(day, int(_num(row[count_col])), _opt(row.get("distance")), _opt(row.get("calorie")))
            if item.steps < 0:
                raise Junk("negative steps")
            if day not in steps or item.steps > steps[day].steps:
                steps[day] = item
    elif type_name == "exercise":
        def build(row):
            start, end = parse_utc(row["start_time"]), parse_utc(row["end_time"])
            duration_ms = _opt(row.get("duration"))
            minutes = duration_ms / 60000 if duration_ms else (end - start).total_seconds() / 60
            kcal = _opt(row.get("calorie"))
            ex.workouts.append(WorkoutRec(
                row["datauuid"], start, end, r.tz(row), int(_num(row["exercise_type"])), round(minutes, 2),
                kcal if kcal is not None else _opt(row.get("total_calorie")), _opt(row.get("distance")),
                _opt(row.get("mean_heart_rate")), _opt(row.get("max_heart_rate")), row.get("deviceuuid", "")))
    elif type_name == "weight":
        def build(row):
            start, tz = parse_utc(row["start_time"]), r.tz(row)
            values = {kind: _opt(row.get(col)) for col, kind in BODY_KINDS.items()}
            height = _opt(row.get("height"))
            if height is None and all(v is None for v in values.values()):
                raise Junk("no values")
            if height is not None:
                heights.append((start, height))
            for kind, value in values.items():
                if value is None or value <= 0:  # a 0 must not hide the day's earlier real weigh-in
                    continue
                rec = BodyRec(start, tz, kind, value)
                key = (rec.local_date, kind)
                if key not in body or start >= body[key].start_utc:  # several weigh-ins a day: the last one
                    body[key] = rec
    else:
        raise AssertionError(type_name)

    _each(r, rows, type_name, build)


def _read_binned(r: _Reader, info: zipfile.ZipInfo, type_name: str) -> None:
    """Rows first (the CSV is closed before any detail file is opened), then each row's detail file.

    Heart rate: the CSV row is an hourly summary; its detail file holds ~1-minute bins, which replace the row. The row
    itself is kept only when it has no detail file."""
    rows = r.rows(info, type_name)
    if rows is None:
        return
    pending: list[tuple[str, int, float | None, float | None, dt.datetime, dt.datetime]] = []

    def collect(row):
        start = parse_utc(row["start_time"])
        end = parse_utc(row["end_time"]) if (row.get("end_time") or "").strip() else start
        ref = (row.get("binning_data") or "").strip()
        if ref.endswith(".bin"):
            uuid = ref[:-4]
        elif ref:  # heart rate names the detail file itself: `<datauuid>.com.samsung.health.heart_rate...json`
            uuid = ref.split(".", 1)[0]
        else:
            uuid = (row.get("datauuid") or "").strip()
        if type_name == "tracker.heart_rate":
            # the hourly value is only a fallback: an empty one is fine when the detail file exists; a non-positive
            # one is never used (a missing detail file then makes the row junk)
            extra, fallback_value = _opt(row.get("min")), _opt(row.get("heart_rate"))
            if fallback_value is not None and fallback_value <= 0:
                fallback_value = None
        else:
            extra = _opt(row.get("baseline")) if type_name == "skin_temperature" else None
            fallback = {"skin_temperature": "temperature", "respiratory_rate": "average"}.get(type_name)
            fallback_value = _opt(row.get(fallback)) if fallback else None
        pending.append((uuid, r.tz(row), extra, fallback_value, start, end))

    _each(r, rows, type_name, collect)
    target: list = getattr(r.ex, BINNED[type_name])
    is_hr = type_name == "tracker.heart_rate"
    index = r.bins[type_name]
    for n, (uuid, tz, extra, fallback, start, end) in enumerate(pending, 1):
        detail = index.get(uuid)
        if detail is None:
            if fallback is not None:
                target.append(HrRec(start, end, tz, fallback, extra) if is_hr
                              else BinRec(start, end, tz, fallback, extra))
            else:
                r.junk(type_name)
            continue
        try:
            items = r.read_json(detail)
        except (Junk, ValueError, UnicodeDecodeError):
            r.junk(type_name)
            continue
        finally:
            r.done += detail.file_size
        for item in items:
            try:
                if not isinstance(item, dict):
                    raise Junk("item")
                if is_hr:
                    hr = _num(item.get("heart_rate"))
                    if hr <= 0:
                        raise Junk("no heart rate")
                    target.append(HrRec(_ms(item.get("start_time")), _ms(item.get("end_time")), tz, hr,
                                        _opt(item.get("heart_rate_min"))))
                    continue
                if type_name == "hrv":
                    value, value2 = _num(item.get("sdnn")), _opt(item.get("rmssd"))
                elif type_name == "skin_temperature":
                    value, value2 = _num(item.get("mean")), extra
                else:
                    value, value2 = _num(item.get("respiratory_rate")), None
                target.append(BinRec(_ms(item.get("start_time")), _ms(item.get("end_time")), tz, value, value2))
            except Junk:
                r.junk(type_name)
        if n % 200 == 0:
            r.report(type_name)


# The order types are read in (all independent).
ORDER = ["sleep", "sleep_stage", "hrv", "skin_temperature", "respiratory_rate", "tracker.oxygen_saturation",
         "tracker.heart_rate", "tracker.pedometer_day_summary", "step_daily_trend", "stress", "exercise", "weight"]


def read_export(path: Path, progress: Callable[[float, str], None] | None = None, *,
                default_tz_min: int = 0) -> Export:
    """Reads the export at `path`. `progress(fraction, stage)` is called as work proceeds and ends at 1.0.
    `default_tz_min` is used for rows without a `time_offset` (pass the app's configured zone)."""
    ex = Export()
    with zipfile.ZipFile(path) as zf:
        r = _Reader(zf, ex, default_tz_min, progress)
        csvs: dict[str, list[zipfile.ZipInfo]] = {}
        for info in zf.infolist():
            if info.is_dir():
                continue
            m = _JSON_NAME.search(info.filename)
            if m:
                if m.group(1) in r.bins:
                    r.bins[m.group(1)][m.group(2)] = info
                continue
            m = _CSV_NAME.search(info.filename)
            if m and "/jsons/" not in info.filename:
                csvs.setdefault(m.group(1), []).append(info)

        for type_name in csvs:
            if type_name not in REQUIRED:
                ex.skipped[type_name] = "not imported"
        r.total = max(1, sum(i.file_size for t in ORDER for i in csvs.get(t, []))
                      + sum(i.file_size for t in BINNED if t in csvs for i in r.bins[t].values()))
        r.report("start")

        steps: dict[dt.date, StepsDay] = {}
        body: dict[tuple[dt.date, str], BodyRec] = {}
        heights: list[tuple[dt.datetime, float]] = []
        for type_name in ORDER:
            for info in csvs.get(type_name, []):
                if type_name in BINNED:
                    _read_binned(r, info, type_name)
                else:
                    _read_type(r, info, type_name, steps, body, heights)
                r.done += info.file_size
                r.report(type_name)

    ex.steps = sorted(steps.values(), key=lambda s: s.local_date)
    ex.body = sorted(body.values(), key=lambda b: (b.start_utc, b.kind))
    ex.latest_height_cm = max(heights)[1] if heights else None
    for name in ("sleep", "stages", "hrv", "skin", "resp", "spo2", "hr", "steps", "stress", "workouts", "body"):
        ex.counts[name] = len(getattr(ex, name))
    r.report("done", final=True)
    return ex
