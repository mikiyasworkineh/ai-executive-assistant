"""Reset the demo data (local SQLite mirror + the Google events the app booked).

Usage (from the repo root, backend stopped or running - both work):

    python backend/reset_demo.py                # dry run: shows what would change
    python backend/reset_demo.py --yes          # clear local tables + Google events
    python backend/reset_demo.py --yes --seed   # clear, then insert demo rows
    python backend/reset_demo.py --yes --keep-google   # local only

What it touches:
  * local tables: calendar_events, tasks, emails, action_logs  (always cleared)
  * Google Calendar: only events that exist in the local mirror (i.e. booked by
    this app). Events you created directly in Google Calendar are never touched.

It does NOT delete the database file, so you can keep the app running.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.calendar_api import delete_remote_event, is_remote_id  # noqa: E402
from backend.app.config import DB_PATH  # noqa: E402

TABLES = ("calendar_events", "tasks", "emails", "action_logs")


def _counts(conn) -> dict:
    return {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in TABLES
    }


def _seed(conn) -> None:
    """Same demo rows the app inserts on a fresh install."""
    from backend.app.config import now_local, today_local

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="actually delete (otherwise dry run)")
    parser.add_argument("--seed", action="store_true", help="insert demo events and tasks afterwards")
    parser.add_argument("--keep-google", action="store_true", help="do not touch Google Calendar")
    parser.add_argument("--db", default=None, help="alternate database file (default: backend/executive_assistant.db)")
    args = parser.parse_args()

    db_path = os.path.abspath(args.db) if args.db else DB_PATH
    if not os.path.exists(db_path):
        print(f"No database yet at {db_path} - start the backend once and it will be created.")
        return 0

    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        print(f"Database: {db_path}")
        print("Current rows:", _counts(conn))

        mirrored = conn.execute(
            "SELECT id, gcal_id, title FROM calendar_events"
        ).fetchall()
        google_events = [
            row for row in mirrored if is_remote_id(row[1])
        ]

        if args.keep_google:
            print(f"Google Calendar: keeping {len(google_events)} mirrored event(s) (--keep-google)")
        else:
            print(f"Google Calendar: {len(google_events)} event(s) would be deleted")
            for _id, gcal_id, title in google_events:
                print(f"  - {title} ({gcal_id})")

        if not args.yes:
            print("\nDry run. Re-run with --yes to apply.")
            return 0

        if not args.keep_google:
            for _id, gcal_id, title in google_events:
                ok, detail = delete_remote_event(gcal_id)
                print(f"  {'deleted' if ok else 'skipped'}: {title} ({detail})")

        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")
        conn.commit()

        if args.seed:
            _seed(conn)
            conn.commit()

        print("\nRemaining rows:", _counts(conn))
        print("Done." + (" Demo data seeded." if args.seed else ""))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
