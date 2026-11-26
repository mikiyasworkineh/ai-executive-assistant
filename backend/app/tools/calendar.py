"""Calendar tools exposed to the agent.

Flow for a booking:
    1. `check_calendar_availability(date)`   - what is already booked
    2. `book_calendar_meeting(...)`          - conflict check + auto-shift,
                                               Google Calendar sync, local mirror

Conflict detection merges the local mirror with **live** Google events, so a
meeting created directly in Google Calendar still blocks the slot. A collision
pushes the meeting to the next free slot instead of double-booking.
"""

from datetime import datetime, timedelta

from ..calendar_api import (
    delete_remote_event,
    events_for_day,
    events_with_ids,
    insert_event,
    patch_event_times,
)
from ..config import now_local
from ..database import connect
from ..tracing import log_action
from ..utils import fmt_time, norm

LOCAL_TIME_FORMAT = "%Y-%m-%dT%H:%M"  # what the model is asked to produce

# Booking a title like "Cancel X" or "CANCELLED: X" means the model tried to
# express a cancellation as a new event. Refuse and point at cancel_event.
INSTRUCTION_PREFIXES = (
    "cancel ", "cancelled ", "canceled ", "delete ", "remove ",
    "reschedule ", "move ", "update ",
)
# Titles that are unambiguously cancellation markers, never real meetings.
CANCEL_MARKERS = ("cancel:", "cancelled:", "canceled:", "deleted:", "removed:")


def _rejection_reason(title: str, busy: list[tuple]) -> str | None:
    """Detects a booking that is really a cancel/reschedule instruction."""
    lowered = norm(title)
    if lowered.startswith(CANCEL_MARKERS):
        return "title contains a cancellation marker"
    if lowered.startswith(INSTRUCTION_PREFIXES) and any(
        norm(event[0]) in lowered for event in busy
    ):
        return "title is an instruction about an existing event"
    return None


# --------------------------------------------------------------------------- #
# Read
# --------------------------------------------------------------------------- #
def check_calendar_availability(date_str: str) -> str:
    """Returns the busy slots for one day (YYYY-MM-DD), local + Google."""
    log_action("Calendar Check", f"Querying calendar availability for {date_str}...")

    conn = connect()
    try:
        rows = [
            tuple(row)
            for row in conn.execute(
                "SELECT title, start_time, end_time, attendees FROM calendar_events "
                "WHERE start_time LIKE ? ORDER BY start_time ASC",
                (f"{date_str}%",),
            ).fetchall()
        ]
    finally:
        conn.close()

    live = events_for_day(date_str)
    if live:
        log_action(
            "Google Calendar Synced",
            f"Pulled {len(live)} event(s) from Google Calendar for {date_str}.",
        )
        seen = {row[0] for row in rows}
        rows += [event for event in live if event[0] not in seen]
        rows.sort(key=lambda row: row[1] or "")

    if not rows:
        log_action("Calendar Free", f"No meetings found on {date_str}. All slots available.")
        return f"No meetings scheduled on {date_str}. The calendar is completely free."

    busy = [f"- '{row[0]}' from {row[1]} to {row[2]} (Attendee: {row[3]})" for row in rows]
    log_action("Calendar Busy Slots", f"Found {len(rows)} existing event(s) on {date_str}.")
    return f"Existing busy slots on {date_str}:\n" + "\n".join(busy)


# --------------------------------------------------------------------------- #
# Write
# --------------------------------------------------------------------------- #
def _busy_slots_for_day(date_str: str) -> list[tuple]:
    """(title, start, end) from local mirror + live Google, deduped by title."""
    conn = connect()
    try:
        rows = [
            tuple(row)
            for row in conn.execute(
                "SELECT title, start_time, end_time FROM calendar_events "
                "WHERE start_time LIKE ?",
                (f"{date_str}%",),
            ).fetchall()
        ]
    finally:
        conn.close()

    live = events_for_day(date_str)
    if not live:
        return rows

    known = {row[0] for row in rows}
    extra = [(e[0], e[1], e[2]) for e in live if e[0] not in known and e[1] and e[2]]
    if extra:
        log_action(
            "Google Calendar Sync",
            f"Including {len(extra)} live Google Calendar event(s) in conflict check.",
        )
    return rows + extra


def _resolve_conflicts(start_time: str, end_time: str, busy: list[tuple]) -> tuple[str, str, bool]:
    """Moves the requested slot forward until it no longer overlaps.

    Returns `(start, end, was_shifted)`. Parsing errors leave the request as-is
    (and are logged) instead of silently booking something unexpected.
    """
    original_start = start_time
    try:
        request_start = datetime.strptime(start_time[:16], LOCAL_TIME_FORMAT)
        request_end = datetime.strptime(end_time[:16], LOCAL_TIME_FORMAT)
        duration = request_end - request_start
        if duration.total_seconds() <= 0:
            duration = timedelta(minutes=30)
            request_end = request_start + duration

        shifted = False
        for _ in range(6):
            overlap = False
            for event_title, event_start_raw, event_end_raw in busy:
                event_start = datetime.strptime(event_start_raw[:16], LOCAL_TIME_FORMAT)
                event_end = datetime.strptime(event_end_raw[:16], LOCAL_TIME_FORMAT)
                if max(request_start, event_start) < min(request_end, event_end):
                    overlap = True
                    shifted = True
                    log_action(
                        "Conflict Resolved",
                        f"Overlap with '{event_title}' "
                        f"({fmt_time(event_start_raw)}-{fmt_time(event_end_raw)}). "
                        f"Auto-shifting to next open slot at {event_end.strftime('%H:%M')}.",
                    )
                    request_start = event_end
                    request_end = request_start + duration
                    break
            if not overlap:
                break

        return (
            request_start.strftime(LOCAL_TIME_FORMAT),
            request_end.strftime(LOCAL_TIME_FORMAT),
            shifted,
        )
    except Exception as error:  # noqa: BLE001 - bad input must not book blindly
        log_action("Conflict Check Skipped", f"Could not evaluate conflicts: {str(error)[:120]}")
        return start_time, end_time, False


def book_calendar_meeting(
    title: str,
    start_time: str,
    end_time: str,
    attendee_email: str,
    description: str,
) -> str:
    """Books a meeting in Google Calendar (auto-shifting out of conflicts).

    start_time / end_time must look like '2026-11-26T15:00' and are interpreted
    in APP_TIMEZONE.
    """
    log_action("Slot Verification", f"Checking conflict for '{title}' ({start_time} to {end_time})...")

    date_prefix = start_time[:10]
    requested_start = start_time
    busy = _busy_slots_for_day(date_prefix)

    rejection = _rejection_reason(title, busy)
    if rejection:
        log_action("Booking Rejected", f"Refused '{title}' ({rejection}).")
        return (
            f"Not booked: '{title}' {rejection}. Use cancel_event(title) to delete an "
            "event or reschedule_event(title, new_start, new_end) to move it. "
            "Never book a new event to represent a cancellation."
        )

    start_time, end_time, shifted = _resolve_conflicts(start_time, end_time, busy)

    event_id, synced = insert_event(title, start_time, end_time, attendee_email, description)
    if not event_id:
        event_id = f"gcal_{int(datetime.now().timestamp())}"  # local-only id

    conn = connect()
    try:
        conn.execute(
            "INSERT INTO calendar_events "
            "(gcal_id, title, start_time, end_time, attendees, description) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, title, start_time, end_time, attendee_email, description),
        )
        conn.commit()
    finally:
        conn.close()

    if shifted:
        message = (
            f"Conflict detected at {requested_start}! Automatically shifted and booked "
            f"'{title}' at next open slot: {start_time} to {end_time} with {attendee_email}."
        )
    else:
        message = f"Booked '{title}' with {attendee_email} from {start_time} to {end_time}."
        if not synced:
            message += " (saved locally; Google Calendar sync is not configured)"
    log_action("Calendar Booked", message)
    return message


# --------------------------------------------------------------------------- #
# Lookup / modify individual events
# --------------------------------------------------------------------------- #
def _candidate_events(date_str: str = "", days: int = 7) -> list[dict]:
    """Local mirror + live Google events over a date window.

    Each candidate: {title, start, end, attendees, gcal_id, local_id}.
    """
    start_day = datetime.strptime(date_str or now_local().strftime("%Y-%m-%d"), "%Y-%m-%d")
    day_list = [(start_day + timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(max(1, days))]

    candidates: list[dict] = []
    conn = connect()
    try:
        for day in day_list:
            for row in conn.execute(
                "SELECT id, gcal_id, title, start_time, end_time, attendees "
                "FROM calendar_events WHERE start_time LIKE ? ORDER BY start_time ASC",
                (f"{day}%",),
            ).fetchall():
                candidates.append(
                    {
                        "local_id": row[0],
                        "gcal_id": row[1],
                        "title": row[2],
                        "start": row[3],
                        "end": row[4],
                        "attendees": row[5],
                    }
                )
    finally:
        conn.close()

    known_google_ids = {c["gcal_id"] for c in candidates if c["gcal_id"]}
    for day in day_list:
        for event in events_with_ids(day):
            if event["gcal_id"] in known_google_ids:
                continue
            candidates.append({**event, "local_id": None})
    return candidates


def _match_events(query: str, candidates: list[dict]) -> list[dict]:
    """Fuzzy event lookup: exact -> substring -> closest title."""
    needle = norm(query)
    if not needle:
        return []
    exact = [c for c in candidates if norm(c["title"]) == needle]
    if exact:
        return exact
    partial = [c for c in candidates if needle in norm(c["title"]) or norm(c["title"]) in needle]
    if partial:
        return partial
    import difflib

    by_title = {norm(c["title"]): c for c in candidates}
    close = difflib.get_close_matches(needle, list(by_title), n=3, cutoff=0.6)
    return [by_title[title] for title in close]


def list_events(date: str = "", days: int = 7) -> str:
    """Lists scheduled events (with ids) so they can be inspected or changed.

    `date` defaults to today; `days` widens the window (default 7, max 30).
    ALWAYS call this before cancelling or rescheduling; never invent events.
    """
    days = max(1, min(int(days or 1), 30))
    candidates = _candidate_events(date, days)
    candidates.sort(key=lambda c: c["start"] or "")

    log_action("Event List", f"Listed {len(candidates)} event(s) from {date or 'today'} (+{days}d).")
    if not candidates:
        return f"No events found in the next {days} day(s)."

    lines = [
        f"- {c['title']} | {fmt_time(c['start'])}-{fmt_time(c['end'])} on {str(c['start'])[:10]}"
        f" | attendee: {c['attendees'] or 'none'}"
        for c in candidates
    ]
    return f"Events ({len(candidates)}):\n" + "\n".join(lines)


def cancel_event(title: str, date: str = "") -> str:
    """Deletes an existing event from Google Calendar and the local mirror.

    Use this for cancel / delete / remove requests. Never book a replacement
    or an event whose title contains CANCELLED.
    """
    candidates = _candidate_events(date, days=7)
    matches = _match_events(title, candidates)
    if not matches:
        return (
            f"No event matching '{title}' found in the next 7 days. "
            "Call list_events to see the real schedule; do not book anything to represent a cancellation."
        )
    if len(matches) > 1:
        options = "\n".join(
            f"- {c['title']} on {str(c['start'])[:10]} {fmt_time(c['start'])}-{fmt_time(c['end'])}"
            for c in matches
        )
        return f"Several events match '{title}'. Ask the user which one:\n{options}"

    event = matches[0]
    remote, detail = delete_remote_event(event["gcal_id"])
    if event["local_id"] is not None:
        conn = connect()
        try:
            conn.execute("DELETE FROM calendar_events WHERE id = ?", (event["local_id"],))
            conn.commit()
        finally:
            conn.close()
    elif event["gcal_id"]:
        conn = connect()
        try:
            conn.execute("DELETE FROM calendar_events WHERE gcal_id = ?", (event["gcal_id"],))
            conn.commit()
        finally:
            conn.close()

    if not remote and not event["local_id"]:
        return f"Could not delete '{event['title']}' ({detail}). Nothing was changed."

    message = (
        f"Cancelled '{event['title']}' ({str(event['start'])[:10]} "
        f"{fmt_time(event['start'])}-{fmt_time(event['end'])})."
    )
    if remote:
        message += " Removed from Google Calendar."
    else:
        message += " Removed locally only (Google sync unavailable)."
    log_action("Event Cancelled", message)
    return message


def reschedule_event(title: str, new_start: str, new_end: str, date: str = "") -> str:
    """Moves an existing event to a new slot (conflicts are auto-shifted).

    new_start / new_end use 'YYYY-MM-DDTHH:MM'. Prefer this over booking a
    second event when the user says move / reschedule / push the meeting.
    """
    candidates = _candidate_events(date or new_start[:10], days=1)
    matches = _match_events(title, candidates)
    if not matches:
        return (
            f"No event matching '{title}' found. Call list_events to see the real "
            "schedule; do not book a new event instead."
        )
    if len(matches) > 1:
        options = "\n".join(
            f"- {c['title']} on {str(c['start'])[:10]} {fmt_time(c['start'])}"
            for c in matches
        )
        return f"Several events match '{title}'. Ask the user which one:\n{options}"

    event = matches[0]
    busy = [
        (c["title"], c["start"], c["end"])
        for c in _busy_slots_for_day(new_start[:10])
        if not (c[0] == event["title"] and c[1] == event["start"])
    ]
    start_time, end_time, shifted = _resolve_conflicts(new_start, new_end, busy)

    remote, detail = patch_event_times(event["gcal_id"], start_time, end_time)
    if event["local_id"] is not None:
        conn = connect()
        try:
            conn.execute(
                "UPDATE calendar_events SET start_time = ?, end_time = ? WHERE id = ?",
                (start_time, end_time, event["local_id"]),
            )
            conn.commit()
        finally:
            conn.close()
    else:
        # Event came straight from Google: add it to the local mirror.
        conn = connect()
        try:
            conn.execute(
                "INSERT INTO calendar_events "
                "(gcal_id, title, start_time, end_time, attendees, description) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (event["gcal_id"], event["title"], start_time, end_time,
                 event["attendees"], "Rescheduled by AI assistant"),
            )
            conn.commit()
        finally:
            conn.close()

    message = (
        f"Rescheduled '{event['title']}' to {start_time} - {end_time}"
        f" (was {fmt_time(event['start'])}-{fmt_time(event['end'])} on {str(event['start'])[:10]})."
    )
    if shifted:
        message += " Shifted forward to avoid a conflict."
    if remote:
        message += " Google Calendar updated."
    else:
        message += f" Google sync unavailable ({detail}); local copy updated."
    log_action("Event Rescheduled", message)
    return message
