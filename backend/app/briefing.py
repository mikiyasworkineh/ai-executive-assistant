"""Morning briefing (the "cron" feature).

Two entry points share this logic:
  * the in-process scheduler at BRIEFING_HOUR:BRIEFING_MINUTE
  * POST /api/cron/morning-briefing (for Cloud Scheduler / Task Scheduler)

The email always contains the faithful audit (times + tasks) even if the model
paraphrases the narrative, so a meeting can never silently disappear from the
briefing.
"""

from .calendar_api import events_for_day
from .config import APP_TIMEZONE, briefing_recipients, gemini_api_key, gemini_configured, today_local
from .database import connect
from .gemini_client import build_client, generate_with_fallback, response_text
from .tracing import current_trace, log_action, start_trace
from .utils import fmt_time
from .tools.email import send_executive_email


def _todays_agenda(today: str) -> tuple[list[tuple], list[tuple]]:
    """(events, pending tasks) for today, local mirror merged with live Google."""
    conn = connect()
    try:
        events = [
            tuple(row)
            for row in conn.execute(
                "SELECT title, start_time, end_time, attendees FROM calendar_events "
                "WHERE start_time LIKE ? ORDER BY start_time ASC",
                (f"{today}%",),
            ).fetchall()
        ]
        tasks = [
            tuple(row)
            for row in conn.execute(
                "SELECT title, priority, due_date FROM tasks WHERE status = 'pending' "
                "ORDER BY CASE priority WHEN 'Urgent' THEN 1 "
                "WHEN 'Normal' THEN 2 ELSE 3 END"
            ).fetchall()
        ]
    finally:
        conn.close()

    live = events_for_day(today)
    if live:
        known = {event[0] for event in events}
        events += [event for event in live if event[0] not in known]
        log_action(
            "Google Calendar Synced",
            f"Briefing includes {len(live)} live Google Calendar event(s).",
        )
    return events, tasks


def _render(events: list[tuple], tasks: list[tuple]) -> tuple[str, str]:
    """Plain-text schedule and task list used both in the prompt and the email."""
    events_text = "\n".join(
        f"- {fmt_time(e[1])} to {fmt_time(e[2])}: {e[0]} (with {e[3]})" for e in events
    ) or "No meetings scheduled for today."
    tasks_text = "\n".join(
        f"- [{t[1]}] {t[0]} (Due: {t[2]})" for t in tasks
    ) or "No pending tasks."
    return events_text, tasks_text


def _narrative(today: str, events_text: str, tasks_text: str, fallback: str) -> str:
    """Gemini-written briefing; falls back to the plain audit on any failure."""
    if not gemini_configured():
        return fallback

    prompt = f"""
    Write a concise, executive-ready "Morning Executive Briefing" email for a
    startup founder for today ({today}).

    TODAY'S GOOGLE CALENDAR SCHEDULE:
    {events_text}

    PENDING & URGENT TASKS:
    {tasks_text}

    Structure the briefing with:
    1. Schedule Overview & Conflict/Workload Analysis
    2. High-Priority Tasks Due Today
    3. Recommended Focus from your AI Executive Assistant
    """
    try:
        client = build_client(gemini_api_key())
        response, _model = generate_with_fallback(client, prompt=prompt)
        text = response_text(response, "").strip()
        if not text:
            return fallback
        # Keep the authoritative audit below the generated prose.
        return (
            f"{text}\n\n---\n"
            f"Schedule audit for {today} ({APP_TIMEZONE}):\n{events_text}\n\n"
            f"Pending tasks:\n{tasks_text}"
        )
    except Exception:  # noqa: BLE001 - a briefing must still go out
        return fallback


def run_morning_briefing() -> dict:
    """Builds and sends the daily briefing. Safe to call repeatedly."""
    start_trace()
    log_action("Cron Webhook", "Proactive Morning Briefing job triggered (Cloud Scheduler / Cron)...")

    today = today_local()
    events, tasks = _todays_agenda(today)
    log_action(
        "Daily Audit",
        f"Audited {len(events)} calendar events and {len(tasks)} pending tasks for {today}.",
    )

    events_text, tasks_text = _render(events, tasks)
    fallback = (
        f"Morning Executive Briefing ({today})\n\n"
        f"Schedule:\n{events_text}\n\nTasks:\n{tasks_text}"
    )
    body = _narrative(today, events_text, tasks_text, fallback)

    recipients = briefing_recipients()
    for recipient in recipients:
        send_executive_email(
            to_email=recipient,
            subject=f"\u2600\ufe0f Proactive Morning Executive Briefing ({today})",
            body=body,
        )

    log_action("Briefing Dispatched", f"Morning Executive Briefing sent to {', '.join(recipients)}.")
    return {
        "status": "success",
        "recipients": recipients,
        "briefing": body,
        "trace": current_trace(),
    }
