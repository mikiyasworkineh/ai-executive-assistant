"""Google Calendar access layer.

Two credential styles are supported:

* OAuth token (`token.json`) - acts as the user, can invite guests.
* Service account (`service_account.json`) - the calendar must be shared with
  the service-account address; Google forbids these from inviting attendees.

`CALENDAR_BACKEND` in `.env` picks one ("auto" prefers OAuth when a token
exists). Nothing here writes to the local database; that is the tool layer.
"""

import os
from datetime import datetime, timedelta

from .config import (
    APP_TIMEZONE,
    CALENDAR_BACKEND,
    GOOGLE_CALENDAR_SCOPES,
    gcal_config,
    local_tz,
)
from .tracing import log_action
from .utils import split_emails


def oauth_token_present() -> bool:
    cfg = gcal_config()
    return os.path.exists(cfg["oauth_token_file"]) and os.path.exists(
        cfg["oauth_client_file"]
    )


def service_key_present() -> bool:
    return os.path.exists(gcal_config()["service_account_file"])


def calendar_backend() -> str:
    """Resolved backend: 'oauth', 'service_account' or 'none'."""
    oauth_ready = oauth_token_present()
    key_ready = service_key_present()

    if CALENDAR_BACKEND == "oauth":
        return "oauth" if oauth_ready else "none"
    if CALENDAR_BACKEND in ("service_account", "service-account", "sa"):
        return "service_account" if key_ready else "none"
    # auto
    if oauth_ready:
        return "oauth"
    return "service_account" if key_ready else "none"


def _build_service():
    cfg = gcal_config()
    from googleapiclient.discovery import build

    backend = calendar_backend()
    if backend == "oauth":
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_file(
            cfg["oauth_token_file"], GOOGLE_CALENDAR_SCOPES
        )
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(cfg["oauth_token_file"], "w", encoding="utf-8") as handle:
                handle.write(creds.to_json())
        if not creds or not creds.valid:
            raise RuntimeError("OAuth token invalid. Re-run: python backend/google_oauth.py")
        return build("calendar", "v3", credentials=creds)

    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(
        cfg["service_account_file"], scopes=GOOGLE_CALENDAR_SCOPES
    )
    return build("calendar", "v3", credentials=creds)


def get_service():
    """Calendar API client for the configured backend, or None if unusable."""
    cal_id = gcal_config()["calendar_id"]
    if "your_email" in cal_id or calendar_backend() == "none":
        return None

    try:
        return _build_service()
    except Exception as error:  # noqa: BLE001 - degrade to local-only mode
        print(f"Google Calendar ({calendar_backend()}) unavailable: {error}", flush=True)
        return None


def day_bounds(date_str: str) -> tuple[str | None, str | None]:
    """[start, end) of a local day as RFC3339 strings."""
    try:
        start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=local_tz())
    except ValueError:
        return None, None
    return start.isoformat(), (start + timedelta(days=1)).isoformat()


def events_for_day(date_str: str) -> list[tuple]:
    """Live Google events for one day: (title, start, end, attendees)."""
    service = get_service()
    time_min, time_max = day_bounds(date_str)
    if not service or not time_min:
        return []

    try:
        result = (
            service.events()
            .list(
                calendarId=gcal_config()["calendar_id"],
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
    except Exception as error:  # noqa: BLE001 - an empty day is a safe fallback
        print(f"Google Calendar list note: {error}", flush=True)
        return []

    events = []
    for item in result.get("items", []):
        if item.get("status") == "cancelled":
            continue
        start = (item.get("start") or {}).get("dateTime") or (item.get("start") or {}).get("date")
        end = (item.get("end") or {}).get("dateTime") or (item.get("end") or {}).get("date")
        attendees = ", ".join(
            person.get("email", "")
            for person in item.get("attendees", [])
            if person.get("email")
        )
        events.append((item.get("summary", "(no title)"), start, end, attendees))
    return events


def insert_event(title: str, start_time: str, end_time: str, attendee_email: str, description: str):
    """Creates the event in Google Calendar.

    Returns `(event_id, synced)`. When the service account cannot invite
    guests, the event is retried without attendees instead of failing.
    """
    service = get_service()
    if not service:
        return None, False

    cal_id = gcal_config()["calendar_id"]
    attendees = split_emails(attendee_email)

    body = {
        "summary": title,
        "description": f"{description} | Attendee: {attendee_email}",
        "start": {"dateTime": f"{start_time}:00", "timeZone": APP_TIMEZONE},
        "end": {"dateTime": f"{end_time}:00", "timeZone": APP_TIMEZONE},
    }
    if attendees:
        body["attendees"] = [{"email": address} for address in attendees]

    try:
        created = (
            service.events()
            .insert(
                calendarId=cal_id,
                body=body,
                sendUpdates="all" if attendees else "none",
            )
            .execute()
        )
    except Exception as error:  # noqa: BLE001 - service accounts cannot invite
        if not attendees or "invite attendees" not in str(error).lower():
            print(f"Google Calendar API live sync note: {error}", flush=True)
            log_action("Google Calendar Error", f"Live sync failed: {str(error)[:160]}")
            return None, False

        log_action(
            "Invite Unsupported",
            "Service account cannot invite guests; creating the event without invites.",
        )
        body.pop("attendees", None)
        body["description"] += (
            " | Invite NOT sent (run backend/google_oauth.py or use domain delegation)"
        )
        try:
            created = (
                service.events()
                .insert(calendarId=cal_id, body=body, sendUpdates="none")
                .execute()
            )
        except Exception as retry_error:  # noqa: BLE001 - keep local booking
            print(f"Google Calendar API live sync note: {retry_error}", flush=True)
            log_action("Google Calendar Error", f"Live sync failed: {str(retry_error)[:160]}")
            return None, False

    event_id = created.get("id")
    log_action(
        "Google Calendar Synced",
        f"Created event {event_id} on Google Calendar ({cal_id}, TZ {APP_TIMEZONE}).",
    )
    return event_id, True


# --------------------------------------------------------------------------- #
# Lookup / modify individual events
# --------------------------------------------------------------------------- #
def is_remote_id(event_id) -> bool:
    """True when the id is a real Google event id (not a local placeholder)."""
    return bool(event_id) and not str(event_id).startswith(("gcal_", "evt_"))


def events_with_ids(date_str: str) -> list[dict]:
    """Live Google events for one day, including their ids and attendee list."""
    service = get_service()
    time_min, time_max = day_bounds(date_str)
    if not service or not time_min:
        return []

    try:
        result = (
            service.events()
            .list(
                calendarId=gcal_config()["calendar_id"],
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
    except Exception as error:  # noqa: BLE001 - treat as "no events"
        print(f"Google Calendar list note: {error}", flush=True)
        return []

    events = []
    for item in result.get("items", []):
        if item.get("status") == "cancelled":
            continue
        events.append(
            {
                "gcal_id": item.get("id"),
                "title": item.get("summary", "(no title)"),
                "start": (item.get("start") or {}).get("dateTime")
                or (item.get("start") or {}).get("date"),
                "end": (item.get("end") or {}).get("dateTime")
                or (item.get("end") or {}).get("date"),
                "attendees": ", ".join(
                    person.get("email", "")
                    for person in item.get("attendees", [])
                    if person.get("email")
                ),
            }
        )
    return events


def delete_remote_event(event_id: str) -> tuple[bool, str]:
    """Deletes one Google Calendar event. Returns (deleted, message)."""
    service = get_service()
    if not service or not is_remote_id(event_id):
        return False, "not a Google event"
    try:
        service.events().delete(
            calendarId=gcal_config()["calendar_id"], eventId=event_id
        ).execute()
        return True, "deleted"
    except Exception as error:  # noqa: BLE001 - 404/410 means already gone
        status = getattr(error, "status_code", None) or getattr(
            getattr(error, "resp", None), "status", None
        )
        if status in (404, 410):
            return True, "already absent"
        print(f"Google Calendar delete note: {error}", flush=True)
        return False, str(error)[:160]


def patch_event_times(event_id: str, start_time: str, end_time: str) -> tuple[bool, str]:
    """Moves a Google event to a new slot. Returns (updated, message)."""
    service = get_service()
    if not service or not is_remote_id(event_id):
        return False, "not a Google event"
    try:
        service.events().patch(
            calendarId=gcal_config()["calendar_id"],
            eventId=event_id,
            body={
                "start": {"dateTime": f"{start_time}:00", "timeZone": APP_TIMEZONE},
                "end": {"dateTime": f"{end_time}:00", "timeZone": APP_TIMEZONE},
            },
        ).execute()
        return True, "updated"
    except Exception as error:  # noqa: BLE001 - fall back to local mirror
        print(f"Google Calendar patch note: {error}", flush=True)
        return False, str(error)[:160]
