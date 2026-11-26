"""Agent tools (Gemini function calling).

Everything listed in `ALL_TOOLS` is handed to the model. Add a tool here and
it becomes available to the agent automatically.

    calendar  - check_calendar_availability, list_events, book_calendar_meeting,
                cancel_event, reschedule_event
    email     - send_executive_email
    tasks     - list_tasks, add_executive_task, set_task_status
"""

from .calendar import (
    book_calendar_meeting,
    cancel_event,
    check_calendar_availability,
    list_events,
    reschedule_event,
)
from .email import send_executive_email
from .tasks import add_executive_task, list_tasks, set_task_status

ALL_TOOLS = [
    # calendar
    check_calendar_availability,
    list_events,
    book_calendar_meeting,
    cancel_event,
    reschedule_event,
    # email
    send_executive_email,
    # tasks
    list_tasks,
    add_executive_task,
    set_task_status,
]

__all__ = [
    "ALL_TOOLS",
    "check_calendar_availability",
    "list_events",
    "book_calendar_meeting",
    "cancel_event",
    "reschedule_event",
    "send_executive_email",
    "list_tasks",
    "add_executive_task",
    "set_task_status",
]
