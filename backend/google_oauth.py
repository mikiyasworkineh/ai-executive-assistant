"""OPTIONAL: Google Calendar OAuth setup (only needed for real guest invites).

This project uses a SERVICE ACCOUNT by default (see backend/google_auth.py).
You only need this script if you want Google to email invitations to guests,
because Google blocks service accounts from inviting attendees:

    "Service accounts cannot invite attendees without
     Domain-Wide Delegation of Authority."

OAuth makes the backend act as you, so `attendees` + sendUpdates="all" work.

Once token.json exists, CALENDAR_BACKEND=auto prefers OAuth automatically.
Force the service account at any time with CALENDAR_BACKEND=service_account.

Steps:
  1. https://console.cloud.google.com/ -> create/select a project.
  2. Enable "Google Calendar API".
  3. OAuth consent screen -> External -> add yourself as a Test user.
  4. Credentials -> Create credentials -> OAuth client ID -> Desktop app.
  5. Download the JSON and save it as backend/credentials.json
  6. Run this script (from the repo root, with the venv active):
         python backend/google_oauth.py
  7. A browser opens; sign in and approve. token.json is written next to it.
     Refresh tokens are reused automatically by the backend from then on.
"""

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
    client_file = resolve(os.getenv("GOOGLE_OAUTH_CLIENT_SECRET_FILE", "credentials.json"))
    token_file = resolve(os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "token.json"))

    if not os.path.exists(client_file):
        print(f"Missing OAuth client secrets file: {client_file}")
        print("Download it from Google Cloud Console (OAuth client ID -> Desktop app).")
        return 1

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Run: pip install -r backend/requirements.txt")
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(client_file, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(token_file, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    print(f"\nSaved OAuth token to: {token_file}")
    print("Guest invitations are now possible (CALENDAR_BACKEND=auto will use OAuth).")

    try:
        service = build("calendar", "v3", credentials=creds)
        calendars = service.calendarList().list(maxResults=5).execute().get("items", [])
        print("\nCalendars visible to this token:")
        for cal in calendars:
            marker = " (primary)" if cal.get("primary") else ""
            print(f"  - {cal.get('summary')}{marker}  id={cal.get('id')}")
    except Exception as e:
        print(f"\nToken saved, but calendar list failed: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
