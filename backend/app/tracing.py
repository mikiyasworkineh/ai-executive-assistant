"""Per-request execution trace.

Every tool call is recorded twice:

* in `action_logs` (persisted, shown in the dashboard's activity feed)
* in an in-memory list (returned to the UI as the live "Execution Trace")

The in-memory list lives in a `ContextVar` so two concurrent requests never
mix their steps together.
"""

import contextvars

from .config import now_local
from .database import connect

CURRENT_EXECUTION_TRACE: contextvars.ContextVar[list | None] = contextvars.ContextVar(
    "execution_trace", default=None
)


def start_trace() -> None:
    """Starts a fresh trace for the current request/job."""
    CURRENT_EXECUTION_TRACE.set([])


def current_trace() -> list:
    """The trace of the current request (empty when no trace was started)."""
    return CURRENT_EXECUTION_TRACE.get() or []


def log_action(step_type: str, message: str) -> None:
    """Records one step of the agent workflow."""
    timestamp = now_local().strftime("%H:%M:%S")

    trace = CURRENT_EXECUTION_TRACE.get()
    if trace is not None:
        trace.append(
            {"step_type": step_type, "message": message, "timestamp": timestamp}
        )

    conn = connect()
    try:
        conn.execute(
            "INSERT INTO action_logs (step_type, message, timestamp) VALUES (?, ?, ?)",
            (step_type, message, timestamp),
        )
        conn.commit()
    finally:
        conn.close()
