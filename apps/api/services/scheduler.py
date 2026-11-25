"""Opt-in background jobs (ENABLE_SCHEDULER=1); off by default so nothing contacts the internet unasked."""
from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler

from services.environment_cron import run_scheduled_refresh

REFRESH_HOURS = 3


def build_scheduler(job: Callable[[], None]) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(job, "interval", hours=REFRESH_HOURS, id="environment-refresh")
    return scheduler


def start_scheduler() -> BackgroundScheduler:
    scheduler = build_scheduler(run_scheduled_refresh)
    scheduler.start()
    return scheduler
