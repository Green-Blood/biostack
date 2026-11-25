"""Writes finished wearable data into the database. Deriving days from raw records lives in wearable_derive."""
import dataclasses
import datetime as dt

from sqlmodel import Session, select

from db.models import DEMO_SOURCE, DailyMetric, SleepSession, SleepStage, Workout
from services import profile as profile_svc
from services.metrics_store import INTEGER_FIELDS

DAILY_FIELDS = set(DailyMetric.model_fields) - {"metric_date", "source", "field_sources"}


@dataclasses.dataclass(frozen=True)
class UpsertCount:
    added: int = 0
    updated: int = 0
    unchanged: int = 0


@dataclasses.dataclass(frozen=True)
class StageIn:
    external_id: str
    start_utc: dt.datetime
    end_utc: dt.datetime
    stage: str  # awake | light | deep | rem


@dataclasses.dataclass(frozen=True)
class SleepIn:
    external_id: str
    start_utc: dt.datetime
    end_utc: dt.datetime
    tz_offset_min: int
    wake_date: dt.date
    duration_min: float
    deep_min: float = 0
    rem_min: float = 0
    light_min: float = 0
    awake_min: float = 0
    efficiency: float | None = None
    sleep_type: str = ""
    is_main: bool = True
    device_id: str = ""


@dataclasses.dataclass(frozen=True)
class WorkoutIn:
    external_id: str
    start_utc: dt.datetime
    end_utc: dt.datetime
    tz_offset_min: int
    local_date: dt.date
    type_code: int
    duration_min: float
    kcal: float | None = None
    distance_m: float | None = None
    hr_avg: float | None = None
    hr_max: float | None = None
    device_id: str = ""


# Fields that describe one thing together: a night's sleep comes from one source, and so does its HRV. When another
# source already holds any field of a group on a day, the whole group is left to it (and this source's own older
# values in the group are cleared), so a night is never a mix of two recordings.
FIELD_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"sleep_total_min", "sleep_deep_min", "sleep_rem_min", "sleep_light_min", "sleep_awake_min", "sleep_efficiency"}),
    frozenset({"hrv_sdnn", "hrv_rmssd"}),
)


def _owner(row: DailyMetric, sources: dict, field: str) -> str | None:
    if getattr(row, field) is None:
        return None
    return sources.get(field) or row.source  # legacy rows: the row source owns what it holds


def ingest_daily(session: Session, days: dict[dt.date, dict[str, float]], source: str, *, complete: bool = False) -> int:
    """Write a field only when it is empty or an earlier write from the same source put it there.

    Fields written by hand or by the phone sync are never replaced. A real import landing on a demo day replaces the
    whole day, as in metrics_store. Grouped fields (FIELD_GROUPS) are written all-or-nothing per day.

    `complete=True` says each given day holds everything `source` derives for it (a full export): fields `source` wrote
    earlier that are missing now are cleared, and a row left with no values is deleted. Other sources' fields are never
    touched. Returns how many fields were written."""
    written = 0
    for day, fields in days.items():
        incoming = {f: v for f, v in fields.items() if f in DAILY_FIELDS and v is not None}
        row = session.get(DailyMetric, day)
        if row is not None and row.source == DEMO_SOURCE and source != DEMO_SOURCE:
            if not incoming:
                continue  # nothing to put in its place: a demo day stays until real data replaces it
            session.delete(row)
            session.flush()
            row = None
        if row is None and not incoming:
            continue
        row = row or DailyMetric(metric_date=day, source=source)
        sources = dict(row.field_sources or {})
        blocked: set[str] = set()
        for group in FIELD_GROUPS:
            if any(_owner(row, sources, f) not in (None, source) for f in group):
                blocked |= group
        clear = {f for f in DAILY_FIELDS if _owner(row, sources, f) == source
                 and (f in blocked or (complete and f not in incoming))}
        touched = bool(clear)
        for field in clear:
            setattr(row, field, None)
            sources.pop(field, None)
        for field, value in incoming.items():
            if field in blocked or _owner(row, sources, field) not in (None, source):
                continue
            setattr(row, field, round(value) if field in INTEGER_FIELDS else value)
            sources[field] = source
            written += 1
            touched = True
        if not touched:
            continue
        if all(getattr(row, f) is None for f in DAILY_FIELDS):  # only clearing can empty a row, so it is stored
            session.delete(row)
            continue
        row.field_sources = sources
        if row.source != DEMO_SOURCE and not row.source:
            row.source = source
        session.add(row)
    session.commit()
    return written


def _same(row: object, incoming: object, fields: list[str]) -> bool:
    return all(getattr(row, f) == getattr(incoming, f) for f in fields)


def ingest_sleep(session: Session, sessions: list[SleepIn], stages: dict[str, list[StageIn]], source: str) -> UpsertCount:
    fields = [f.name for f in dataclasses.fields(SleepIn) if f.name != "external_id"]
    added = updated = unchanged = 0
    for item in sessions:
        incoming_stages = stages.get(item.external_id, [])
        row = session.exec(select(SleepSession).where(SleepSession.source == source,
                                                      SleepSession.external_id == item.external_id)).first()
        if row is None:
            row = SleepSession(source=source, external_id=item.external_id, **{f: getattr(item, f) for f in fields})
            session.add(row)
            session.flush()
            added += 1
        else:
            old = session.exec(select(SleepStage).where(SleepStage.session_id == row.id)).all()
            old_key = sorted((s.external_id, s.start_utc, s.end_utc, s.stage) for s in old)
            new_key = sorted((s.external_id, s.start_utc, s.end_utc, s.stage) for s in incoming_stages)
            if _same(row, item, fields) and old_key == new_key:
                unchanged += 1
                continue
            for f in fields:
                setattr(row, f, getattr(item, f))
            session.add(row)
            for s in old:
                session.delete(s)
            session.flush()
            updated += 1
        for st in incoming_stages:
            session.add(SleepStage(session_id=row.id, external_id=st.external_id, start_utc=st.start_utc,
                                   end_utc=st.end_utc, stage=st.stage))
    session.commit()
    return UpsertCount(added, updated, unchanged)


def ingest_workouts(session: Session, items: list[WorkoutIn], source: str) -> UpsertCount:
    fields = [f.name for f in dataclasses.fields(WorkoutIn) if f.name != "external_id"]
    added = updated = unchanged = 0
    for item in items:
        row = session.exec(select(Workout).where(Workout.source == source, Workout.external_id == item.external_id)).first()
        if row is None:
            session.add(Workout(source=source, external_id=item.external_id, **{f: getattr(item, f) for f in fields}))
            added += 1
        elif _same(row, item, fields):
            unchanged += 1
        else:
            for f in fields:
                setattr(row, f, getattr(item, f))
            session.add(row)
            updated += 1
    session.commit()
    return UpsertCount(added, updated, unchanged)


def ingest_body(session: Session, rows: dict[dt.date, dict[str, float]], source: str) -> int:
    """One value per (day, kind); the caller passes the day's last weigh-in. A (day, kind) is written only when it is
    empty or `source` wrote it before: values typed by hand, synced from the phone or imported from a scale CSV are
    never replaced (manual > other existing > import). Returns how many measurements were written."""
    values = {(day, kind): value for day, kinds in rows.items() for kind, value in kinds.items()}
    taken = profile_svc.keys_owned_by_others(session, set(values), source)
    todo = {k: v for k, v in values.items() if k not in taken}
    profile_svc.upsert_measurements(session, todo, source)
    return len(todo)
