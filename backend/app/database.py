"""SQLite access and schema management.

The database is a single file (`backend/executive_assistant.db`) holding four
tables:

    tasks            - to-do items with priority / due date / status
    calendar_events  - local mirror of the meetings the agent booked
    emails           - log of every email the agent drafted/sent
    action_logs      - human-readable step log shown in the dashboard

`calendar_events` is only a mirror: the source of truth for meetings is Google
Calendar. Google events that were not created here are read live and never
persisted.
"""

import sqlite3

from .config import DB_PATH, SEED_DEMO_DATA, now_local, today_local

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    priority TEXT DEFAULT 'Normal',
    due_date TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gcal_id TEXT,
    title TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    attendees TEXT,
    description TEXT,
    source TEXT DEFAULT 'Google Calendar API'
);

CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT,
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS action_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    step_type TEXT,
    message TEXT,
    timestamp TEXT
);
"""


def connect(row_factory=None) -> sqlite3.Connection:
    """Opens the application database. Caller is responsible for closing."""
    conn = sqlite3.connect(DB_PATH)
    if row_factory is not None:
        conn.row_factory = row_factory
    return conn


def init_db() -> None:
    """Creates the schema and, on an empty install, seeds demo data."""
    conn = connect()
    try:
        c = conn.cursor()
        c.executescript(SCHEMA)
        if SEED_DEMO_DATA:
            _seed_demo_rows(c)
        conn.commit()
    finally:
        conn.close()


def _seed_demo_rows(c: sqlite3.Cursor) -> None:
    """Inserts a realistic founder schedule, only when the tables are empty."""
    today = today_local()

    if c.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0] == 0:
        c.executemany(
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

    if c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0:
        c.executemany(
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
