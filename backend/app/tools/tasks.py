"""Task board tools: list, add and change the status of to-dos.

Design notes
------------
* Tasks never block calendar time - they are reminders with a due *date*.
* Titles are matched fuzzily (exact -> substring -> closest match) so the
  agent can work with "the Q4 budget task" instead of the full title.
* `add_executive_task` refuses to create duplicates and refuses to create
  meta-tasks such as "Mark X as complete" (that is what `set_task_status` is
  for). Without that guard, a "mark it done" request used to create a brand
  new task carrying the instruction as its title.
"""

import difflib

from ..config import now_local, today_local
from ..database import connect
from ..tracing import log_action
from ..utils import norm

PRIORITIES = ("Urgent", "Normal", "Low")

COMPLETED_WORDS = ("done", "complete", "completed", "finished", "closed")
PENDING_WORDS = ("pending", "todo", "open", "reopen", "not done", "incomplete")

# Titles starting with these are instructions, not new work.
INSTRUCTION_PREFIXES = ("mark ", "set ", "change ", "update ", "complete ", "close ")


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #
def load_tasks(status: str = "all") -> list[tuple]:
    """Rows as (id, title, priority, due_date, status), newest first."""
    conn = connect()
    try:
        if status in ("pending", "completed"):
            rows = conn.execute(
                "SELECT id,title,priority,due_date,status FROM tasks "
                "WHERE status = ? ORDER BY id DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id,title,priority,due_date,status FROM tasks ORDER BY id DESC"
            ).fetchall()
    finally:
        conn.close()
    return [tuple(row) for row in rows]


def match_tasks(query: str) -> list[tuple]:
    """Fuzzy task lookup: exact -> substring -> closest title."""
    needle = norm(query)
    if not needle:
        return []

    rows = load_tasks("all")
    exact = [row for row in rows if norm(row[1]) == needle]
    if exact:
        return exact

    partial = [row for row in rows if needle in norm(row[1]) or norm(row[1]) in needle]
    if partial:
        return partial

    by_title = {norm(row[1]): row for row in rows}
    close = difflib.get_close_matches(needle, list(by_title), n=3, cutoff=0.55)
    return [by_title[title] for title in close]


def list_tasks(status: str = "all") -> str:
    """Lists the executive's tasks. ALWAYS call this before reporting tasks."""
    status = (status or "all").strip().lower()
    if status in COMPLETED_WORDS:
        status = "completed"
    if status not in ("pending", "completed", "all"):
        status = "all"

    rows = load_tasks(status)
    log_action("Task List", f"Listed {len(rows)} task(s) ({status}).")
    if not rows:
        return f"No {status} tasks found."

    lines = [
        f"{row[0]}. [{row[2]}] {row[1]} (Due: {row[3]}, Status: {row[4]})"
        for row in rows
    ]
    return f"Tasks ({status}):\n" + "\n".join(lines)


# --------------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------------- #
def add_executive_task(title: str, priority: str, due_date: str) -> str:
    """Adds a NEW task. Only for genuinely new work; see set_task_status()."""
    title = (title or "").strip()
    due_date = (due_date or "").strip() or today_local()
    if priority not in PRIORITIES:
        priority = "Normal"

    existing = load_tasks("all")
    new_norm = norm(title)

    # 1) Duplicate protection (any status, not just pending).
    for task in existing:
        if norm(task[1]) == new_norm:
            log_action("Task Skipped", f"Task '{task[1]}' already exists (id {task[0]}, {task[4]}).")
            if task[4] == "completed":
                return (
                    f"Task '{task[1]}' already exists and is completed (id {task[0]}). "
                    "Nothing added; use set_task_status to reopen it if needed."
                )
            return f"Task '{task[1]}' already exists (id {task[0]}, {task[4]}); nothing added."

    # 2) Refuse meta-tasks ("Mark 'X' as complete").
    if new_norm.startswith(INSTRUCTION_PREFIXES):
        for task in existing:
            if norm(task[1]) in new_norm:
                log_action("Task Rejected", f"Refused meta-task '{title}'.")
                return (
                    f"Not created: '{title}' looks like an instruction, not a new task. "
                    f"It refers to the existing task '{task[1]}'. "
                    "Use set_task_status(title, 'completed'|'pending') instead."
                )

    conn = connect()
    try:
        conn.execute(
            "INSERT INTO tasks (title, priority, due_date, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (title, priority, due_date, now_local().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()

    log_action("Task Added", f"Created [{priority}] task: '{title}' (Due: {due_date})")
    return f"Added task '{title}' with {priority} priority due on {due_date}."


def set_task_status(title: str, status: str) -> str:
    """Marks an EXISTING task completed or pending (fuzzy title match)."""
    target = (status or "").strip().lower()
    if target in COMPLETED_WORDS:
        target = "completed"
    elif target in PENDING_WORDS:
        target = "pending"
    else:
        return f"Invalid status '{status}'. Use 'completed' or 'pending'."

    matches = match_tasks(title)
    if not matches:
        return (
            f"No task matching '{title}' exists. Call list_tasks to see real task titles; "
            "do not create a task to represent this request."
        )
    if len(matches) > 1:
        options = "\n".join(
            f"- {row[0]}: {row[1]} (Due {row[3]}, {row[4]})" for row in matches
        )
        return f"Several tasks match '{title}'. Ask the user which one:\n{options}"

    task_id, task_title, _priority, due_date, current = matches[0]
    if current == target:
        log_action("Task Unchanged", f"Task '{task_title}' already {target}.")
        return f"Task '{task_title}' is already {target}; nothing changed."

    conn = connect()
    try:
        conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (target, task_id))
        conn.commit()
    finally:
        conn.close()

    log_action("Task Status Updated", f"'{task_title}' -> {target}.")
    return f"Task '{task_title}' is now {target} (was {current}, due {due_date})."
