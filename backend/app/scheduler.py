"""APScheduler wiring for the proactive morning briefing.

The scheduler runs *inside* the API process, so the briefing only fires while
the server is up. For a machine that sleeps, trigger the HTTP endpoint from
Windows Task Scheduler / cron instead (see README notes in diagnostics).
"""

from apscheduler.schedulers.background import BackgroundScheduler

from .briefing import run_morning_briefing
from .config import BRIEFING_HOUR, BRIEFING_MINUTE, local_tz

_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> BackgroundScheduler:
    """Starts the 08:00 briefing job (idempotent)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    tz = local_tz()
    _scheduler = BackgroundScheduler(timezone=tz) if tz else BackgroundScheduler()
    _scheduler.add_job(
        run_morning_briefing,
        "cron",
        hour=BRIEFING_HOUR,
        minute=BRIEFING_MINUTE,
        id="morning_briefing",
        replace_existing=True,
    )
    _scheduler.start()
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
