"""Google Calendar setup check — SERVICE ACCOUNT (the default mode here).

How this project talks to Google Calendar:
  * backend/service_account.json holds the service-account key.
  * The target calendar (GOOGLE_CALENDAR_ID in backend/.env) is shared with the
    service-account address below, with "Make changes to events".
  * The backend signs in as the service account and reads/writes that calendar
    directly. No browser, no consent screen, no token.json needed.

Known Google limitation (not a bug in this project):
  Service accounts cannot invite attendees without Domain-Wide Delegation.
  Events are still created with the guest recorded in the description.
  If real guest invites matter, the optional OAuth path exists
  (backend/google_oauth.py).

One-time setup:
  1. https://console.cloud.google.com/ -> create/select a project.
  2. Enable "Google Calendar API".
  3. IAM & Admin -> Service Accounts -> Create service account.
  4. Keys -> Add key -> Create new key -> JSON -> save as
     backend/service_account.json
  5. Copy the service-account email printed by this script, then open
     Google Calendar -> the target calendar -> Settings and sharing ->
     Share with specific people -> add that email with
     "Make changes to events".
  6. Set GOOGLE_CALENDAR_ID in backend/.env to that calendar's ID
     (your Gmail address, or "primary", or the long ...@group.calendar.google.com id).

Run this script any time to verify the setup:
    python backend/google_auth.py
"""

import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCOPES = ["https://www.googleapis.com/auth/calendar"]

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(BASE_DIR, ".env"))
except Exception:
    pass


def resolve(value: str) -> str:
    return value if os.path.isabs(value) else os.path.join(BASE_DIR, value)


def main() -> int:
    sa_file = resolve(os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json"))
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary").strip() or "primary"

    print("Google Calendar - service account check")
    print(f"  key file    : {sa_file}")
    print(f"  calendar id : {calendar_id}")

    if not os.path.exists(sa_file):
        print("\nFAIL: service-account key not found.")
        print("Download the JSON key from Google Cloud Console and save it as")
        print(f"  {sa_file}")
        return 1

    try:
        info = json.load(open(sa_file, encoding="utf-8"))
    except Exception as e:
        print(f"\nFAIL: cannot read the key file: {e}")
        return 1

    if info.get("type") != "service_account":
        print(f"\nFAIL: that file is not a service-account key (type={info.get('type')!r}).")
        print("Use Credentials -> Service account -> Keys -> JSON.")
        return 1

    sa_email = info.get("client_email", "")
    print(f"  service acct: {sa_email}")

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError as e:
        print(f"\nFAIL: missing dependency: {e}")
        print("Run: pip install -r backend/requirements.txt")
        return 1

    if "your_email" in calendar_id:
        print("\nFAIL: GOOGLE_CALENDAR_ID is still a placeholder in backend/.env")
        print("Set it to your Gmail address (or the calendar ID you shared).")
        return 1

    creds = service_account.Credentials.from_service_account_file(sa_file, scopes=SCOPES)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    try:
        result = (
            service.events()
            .list(calendarId=calendar_id, maxResults=3, singleEvents=True, orderBy="startTime")
            .execute()
        )
        items = result.get("items", [])
        print(f"\nOK: read access confirmed ({len(items)} upcoming event(s) visible).")
        for item in items:
            start = (item.get("start") or {}).get("dateTime") or (item.get("start") or {}).get("date")
            print(f"  - {item.get('summary', '(no title)')} @ {start}")
        return 0
    except HttpError as e:
        print(f"\nFAIL: read access denied ({e.status_code}).")
        print("Share the calendar with the service account address:")
        print(f"  {sa_email}")
        print('Permission must be "Make changes to events".')
        print(f"Details: {str(e)[:300]}")
        return 1
    except Exception as e:
        print(f"\nFAIL: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
