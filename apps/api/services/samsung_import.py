"""Runs one Samsung Health import: parse, derive, then ingest sleep, workouts, daily values and body rows, each in its
own committed batches. Progress: parse 0-60 %, derive 60-70 %, ingest the rest. Logs carry counts only."""
import datetime as dt
import logging
import re
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path

from sqlmodel import Session, select

from db.models import DailyMetric, ImportJob
from services import app_settings
from services.samsung_export import read_export
from services.wearable_derive import derive_body, derive_days, derive_sleep, derive_workouts
from services.wearable_ingest import UpsertCount, ingest_body, ingest_daily, ingest_sleep, ingest_workouts

log = logging.getLogger(__name__)

SOURCE = "samsung_export"
KIND = "samsung_health"
BATCH = 500
_SAMSUNG_CSV = re.compile(r"(?:^|/)com\.samsung\.[^/]*\.csv$")


def looks_like_export(path: Path) -> bool:
    """Cheap check: a readable ZIP whose names include a com.samsung.*.csv file."""
    try:
        with zipfile.ZipFile(path) as zf:
            return any(_SAMSUNG_CSV.search(name) for name in zf.namelist())
    except (zipfile.BadZipFile, OSError):
        return False


def running_job(session: Session) -> ImportJob | None:
    return session.exec(select(ImportJob).where(ImportJob.kind == KIND, ImportJob.status.in_(("queued", "running")))).first()


def create_job(session: Session) -> ImportJob:
    job = ImportJob(kind=KIND, status="queued", started_at=dt.datetime.now(dt.UTC))
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def mark_interrupted(session: Session) -> int:
    """At API start no import can really be running; the ones recorded as such died with the previous process."""
    jobs = session.exec(select(ImportJob).where(ImportJob.status.in_(("queued", "running")))).all()
    for job in jobs:
        job.status, job.error = "failed", "samsung.interrupted"
        job.finished_at = dt.datetime.now(dt.UTC)
        session.add(job)
    session.commit()
    return len(jobs)


def remove_leftover_uploads(data_dir: Path) -> int:
    """At API start no import is running, so any uploaded export still in `data_dir/tmp` was left by a process that
    died mid-import. It holds medical data and must not linger (or reach a backup). Returns how many were removed."""
    folder = data_dir / "tmp"
    if not folder.is_dir():
        return 0
    removed = 0
    for path in folder.glob("samsung-*.zip"):
        path.unlink(missing_ok=True)
        removed += 1
    return removed


def _chunks(items: list, size: int = BATCH) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _add(a: UpsertCount, b: UpsertCount) -> UpsertCount:
    return UpsertCount(a.added + b.added, a.updated + b.updated, a.unchanged + b.unchanged)


def _mark_failed(session: Session, job_id: int) -> None:
    job = session.get(ImportJob, job_id)
    if job is not None and job.status != "failed":
        job.status, job.error, job.stage = "failed", "samsung.failed", job.stage or "parse"
        job.finished_at = dt.datetime.now(dt.UTC)
        session.add(job)
        session.commit()


def run_import(session_factory: Callable[[], Session], zip_path: Path, job_id: int, *, keep_zip: bool = False) -> None:
    """Never raises: the outcome is the job row. The ZIP is deleted afterwards unless `keep_zip` (the CLI's own file).
    Any failure, even in opening the job's session, ends as a failed job (best effort) so nothing stays queued."""
    try:
        with session_factory() as js:  # the job's own session; nothing here uses a request's session
            _run(js, zip_path, job_id)
    except Exception as exc:  # noqa: BLE001
        log.error("samsung import %s failed (%s)", job_id, type(exc).__name__)
        try:
            with session_factory() as fresh:
                _mark_failed(fresh, job_id)
        except Exception as exc2:  # noqa: BLE001
            log.error("samsung import %s: could not record the failure (%s)", job_id, type(exc2).__name__)
    finally:
        if not keep_zip:
            zip_path.unlink(missing_ok=True)


def _run(js: Session, zip_path: Path, job_id: int) -> None:
    last = [-1.0, ""]

    def update(progress: float, stage: str, **fields: object) -> None:
        progress = round(min(max(progress, 0.0), 1.0), 3)
        if not fields and stage == last[1] and progress - last[0] < 0.01:
            return
        last[0], last[1] = progress, stage
        job = js.get(ImportJob, job_id)
        job.progress, job.stage = progress, stage
        for k, v in fields.items():
            setattr(job, k, v)
        js.add(job)
        js.commit()

    try:
        update(0.0, "parse", status="running")
        offset = app_settings.configured_zone(js).utcoffset(dt.datetime.now())
        default_tz = int(offset.total_seconds() // 60) if offset is not None else 0
        export = read_export(zip_path, lambda frac, _stage: update(0.6 * frac, "parse"), default_tz_min=default_tz)

        update(0.6, "derive")
        sessions, stages = derive_sleep(export.sleep, export.stages)
        days = derive_days(export, sessions)
        workouts, dropped = derive_workouts(export)
        body = derive_body(export)
        update(0.7, "derive")

        sleep_count = UpsertCount()
        for part in _chunks(sessions):
            sleep_count = _add(sleep_count, ingest_sleep(js, part, {s.external_id: stages.get(s.external_id, []) for s in part}, SOURCE))
        update(0.8, "sleep")
        work_count = UpsertCount()
        for part in _chunks(workouts):
            work_count = _add(work_count, ingest_workouts(js, part, SOURCE))
        update(0.85, "workouts")
        # The export is a full history: every day from its first to its last derived day is recomputed, including
        # days that already have a row but derive to nothing now (a night that moved to another wake date).
        day_keys = sorted(days)
        if day_keys:
            stored = js.exec(select(DailyMetric.metric_date).where(DailyMetric.metric_date >= day_keys[0],
                                                                   DailyMetric.metric_date <= day_keys[-1])).all()
            day_keys = sorted(set(day_keys) | set(stored))
        for part in _chunks(day_keys):
            ingest_daily(js, {d: days.get(d, {}) for d in part}, SOURCE, complete=True)
        update(0.95, "daily")
        body_n = 0
        for part in _chunks(sorted(body)):
            body_n += ingest_body(js, {d: body[d] for d in part}, SOURCE)

        summary = {
            "counts": dict(export.counts), "skipped": dict(export.skipped), "junk": dict(export.junk),
            "days": len(days), "nights": len({s.wake_date for s in sessions if s.is_main}),
            "workouts": {"added": work_count.added, "updated": work_count.updated, "unchanged": work_count.unchanged},
            "dropped_workouts": dropped, "body": body_n, "latest_height_cm": export.latest_height_cm,
        }
        update(1.0, "done", status="done", summary=summary, finished_at=dt.datetime.now(dt.UTC))
        log.info("samsung import %s done: %s sleep sessions, %s days", job_id, len(sessions), len(days))
    except Exception as exc:  # noqa: BLE001 - the failure belongs to the job row, not to the thread
        log.error("samsung import %s failed (%s)", job_id, type(exc).__name__)
        js.rollback()
        try:
            _mark_failed(js, job_id)
        except Exception as exc2:  # noqa: BLE001
            log.error("samsung import %s: could not record the failure (%s)", job_id, type(exc2).__name__)
            raise
