from __future__ import annotations

import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .pipeline import DailyVideoPipeline


def run_scheduler(pipeline: DailyVideoPipeline) -> None:
    config = pipeline.config.schedule
    if not config.enabled:
        pipeline.run()
        return

    try:
        from apscheduler.schedulers.blocking import BlockingScheduler  # type: ignore
    except ImportError:
        _run_stdlib_scheduler(pipeline)
        return

    scheduler = BlockingScheduler(timezone=config.timezone)
    scheduler.add_job(pipeline.run, "cron", hour=config.hour, minute=config.minute, kwargs={"use_sample_data": False})
    scheduler.start()


def _run_stdlib_scheduler(pipeline: DailyVideoPipeline) -> None:
    schedule = pipeline.config.schedule
    zone = ZoneInfo(schedule.timezone)
    while True:
        now = datetime.now(zone)
        next_run = now.replace(hour=schedule.hour, minute=schedule.minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        sleep_seconds = max((next_run - now).total_seconds(), 1.0)
        time.sleep(sleep_seconds)
        pipeline.run()
