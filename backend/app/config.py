"""Central configuration for the AI Executive Assistant backend.

Everything that comes from `backend/.env` is read here, exactly once, and
exposed as a plain constant or a small helper. The rest of the codebase
imports from this module instead of calling `os.getenv()` directly, so the
whole configuration surface lives in one place.
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# backend/ (this file lives in backend/app/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(BASE_DIR, ".env"))


def resolve_path(value: str) -> str:
    """Makes a config path absolute, relative to backend/."""
    return value if os.path.isabs(value) else os.path.join(BASE_DIR, value)


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
DB_PATH = os.path.join(BASE_DIR, "executive_assistant.db")

# Demo rows keep the dashboard populated on a fresh install. Turn this off
# once the app talks to a real Google Calendar (fake events would otherwise
# block real scheduling).
SEED_DEMO_DATA = _bool(os.getenv("SEED_DEMO_DATA"), default=True)

# --------------------------------------------------------------------------- #
# Time & scheduling
# --------------------------------------------------------------------------- #
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "UTC").strip() or "UTC"


def local_tz() -> ZoneInfo | None:
    """ZoneInfo for APP_TIMEZONE, or None when the name is invalid."""
    try:
        return ZoneInfo(APP_TIMEZONE)
    except Exception:
        return None


def now_local() -> datetime:
    tz = local_tz()
    return datetime.now(tz) if tz else datetime.now()


def today_local() -> str:
    return now_local().strftime("%Y-%m-%d")


BRIEFING_HOUR = int(os.getenv("BRIEFING_HOUR", "8"))
BRIEFING_MINUTE = int(os.getenv("BRIEFING_MINUTE", "0"))

# --------------------------------------------------------------------------- #
# HTTP / security
# --------------------------------------------------------------------------- #
ALLOWED_ORIGINS = _csv(os.getenv("ALLOWED_ORIGINS", "*")) or ["*"]

# When set, every mutating endpoint requires an "X-API-Key" header.
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN", "").strip()

# --------------------------------------------------------------------------- #
# Gemini models
#
# Google regularly returns 503 UNAVAILABLE for the newest models under load,
# so the agent retries and then walks the fallback list.
# --------------------------------------------------------------------------- #
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip()
FALLBACK_MODELS = _csv(os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.8-flash,gemini-3.1-flash-lite"))

GEMINI_ATTEMPTS = max(1, int(os.getenv("GEMINI_ATTEMPTS", "2")))
GEMINI_REQUEST_TIMEOUT_MS = int(os.getenv("GEMINI_REQUEST_TIMEOUT_MS", "30000"))
GEMINI_MAX_SECONDS = int(os.getenv("GEMINI_MAX_SECONDS", "90"))

RETRYABLE_ERROR_HINTS = (
    "503", "unavailable", "429", "resource_exhausted", "500", "internal",
    "overloaded", "high demand", "deadline", "timeout",
)


def gemini_api_key() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip()


def gemini_configured() -> bool:
    key = gemini_api_key()
    return bool(key) and "PASTE_YOUR" not in key


# --------------------------------------------------------------------------- #
# Email (Gmail SMTP)
# --------------------------------------------------------------------------- #
def smtp_config() -> tuple[str, str]:
    """(sender address, app password) as configured, stripped."""
    return (
        os.getenv("SMTP_EMAIL", "").strip(),
        os.getenv("SMTP_APP_PASSWORD", "").strip(),
    )


def smtp_configured() -> bool:
    """True only for real credentials (placeholders keep the app in simulate mode)."""
    email_addr, password = smtp_config()
    return bool(email_addr) and bool(password) and "your_" not in password


def executive_email() -> str:
    value = os.getenv("EXECUTIVE_EMAIL", "founder@startup.io").strip()
    if not value or "your_email" in value:
        return "founder@startup.io"
    return value


def briefing_recipients() -> list[str]:
    return _csv(os.getenv("BRIEFING_RECIPIENTS")) or [executive_email()]


# --------------------------------------------------------------------------- #
# Google Calendar
# --------------------------------------------------------------------------- #
# "auto" | "service_account" | "oauth"  (auto = OAuth token if present, else key)
CALENDAR_BACKEND = os.getenv("CALENDAR_BACKEND", "auto").strip().lower()

GOOGLE_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def gcal_config() -> dict:
    """All calendar-related settings resolved to absolute paths."""
    return {
        "calendar_id": os.getenv("GOOGLE_CALENDAR_ID", "primary").strip() or "primary",
        "oauth_token_file": resolve_path(os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "token.json")),
        "oauth_client_file": resolve_path(
            os.getenv("GOOGLE_OAUTH_CLIENT_SECRET_FILE", "credentials.json")
        ),
        "service_account_file": resolve_path(
            os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json")
        ),
    }
