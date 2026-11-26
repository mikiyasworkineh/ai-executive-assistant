"""Demo data reset.

Shared by the CLI (`backend/reset_demo.py`) and the API endpoint
(`POST /api/demo/reset`) so a demo can be reset from the UI.

Only local tables are deleted by default. Google Calendar is untouched unless
`include_google=True`, and even then only events that this app booked (the
ones present in the local mirror) are removed.
"""

from .calendar_api import delete_remote_event, find_tagged_events, is_remote_id
from .config import now_local, today_local
from .database import connect

TABLES = ("calendar_events", "tasks", "emails", "action_logs")


def demo_counts() -> dict:
    conn = connect()
    try:
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in TABLES
        }
    finally:
        conn.close()


def _seed_demo_rows(conn) -> None:
    """Inserts the same rows `init_db()` creates on a fresh install."""
    today = today_local()
    conn.executemany(
        "INSERT INTO calendar_events "
        "(gcal_id, title, start_time, end_time, attendees, description) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (
                "evt_101",
                "Engineering Sprint Standup",
                f"{today}T10:00",
                f"{today}T10:30",
                "eng-team@startup.io",
                "Daily blocker review and sprint velocity check",
            ),
            (
                "evt_102",
                "Seed Investor Pitch Prep",
                f"{today}T14:00",
                f"{today}T15:00",
                "partner@vc-fund.com",
                "Review Q4 ARR growth metrics and deck",
            ),
        ],
    )
    conn.executemany(
        "INSERT INTO tasks (title, priority, due_date, status, created_at) "
        "VALUES (?, ?, ?, 'pending', ?)",
        [
            (
                "Finalize Q4 investor pitch deck financial slides",
                "Urgent",
                today,
                now_local().isoformat(),
            ),
            (
                "Approve production deployment for v2.1 release",
                "Normal",
                today,
                now_local().isoformat(),
            ),
        ],
    )


def reset_demo_data(*, seed: bool = False, include_google: bool = False) -> dict:
    """Clears the demo tables (and optionally mirrored Google events).

    Returns a summary: what was removed, what remains, and which Google events
    were touched.
    """
    conn = connect()
    try:
        before = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in TABLES
        }

        mirrored = [
            tuple(row)
            for row in conn.execute(
                "SELECT gcal_id, title FROM calendar_events WHERE gcal_id IS NOT NULL"
            ).fetchall()
        ]
        remote = [(gcal_id, title) for gcal_id, title in mirrored if is_remote_id(gcal_id)]

        google_results = []
        if include_google:
            # 1) events listed in the local mirror
            handled = set()
            for gcal_id, title in remote:
                ok, detail = delete_remote_event(gcal_id)
                handled.add(gcal_id)
                google_results.append(
                    {"title": title, "gcal_id": gcal_id, "deleted": ok, "detail": detail}
                )
            # 2) events tagged by this app, even if the mirror was already wiped
            for event in find_tagged_events():
                if event["gcal_id"] in handled:
                    continue
                ok, detail = delete_remote_event(event["gcal_id"])
                google_results.append(
                    {
                        "title": event["title"],
                        "gcal_id": event["gcal_id"],
                        "deleted": ok,
                        "detail": detail,
                    }
                )

        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")

        if seed:
            _seed_demo_rows(conn)

        conn.commit()

        after = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in TABLES
        }
    finally:
        conn.close()

    return {
        "status": "ok",
        "cleared": before,
        "remaining": after,
        "seeded": bool(seed),
        "google_touched": google_results,
    }
