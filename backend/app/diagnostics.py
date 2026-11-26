"""Startup banner and `/api/health` payload.

Both answer the same question: which integrations are real and which are
simulated? That saves "why is nothing in my calendar?" debugging sessions.
"""

from .calendar_api import calendar_backend, oauth_token_present, service_key_present
from .config import (
    API_AUTH_TOKEN,
    APP_TIMEZONE,
    BRIEFING_HOUR,
    BRIEFING_MINUTE,
    CALENDAR_BACKEND,
    FALLBACK_MODELS,
    MODEL_NAME,
    SEED_DEMO_DATA,
    briefing_recipients,
    gcal_config,
    gemini_configured,
    smtp_configured,
)


def health_payload() -> dict:
    cal_id = gcal_config()["calendar_id"]
    return {
        "status": "ok",
        "primary_model": MODEL_NAME,
        "fallback_models": FALLBACK_MODELS,
        "gemini_api_key_configured": gemini_configured(),
        "smtp_configured": smtp_configured(),
        "calendar_backend": calendar_backend(),
        "calendar_backend_mode": CALENDAR_BACKEND,
        "calendar_oauth_token_present": oauth_token_present(),
        "calendar_service_key_present": service_key_present(),
        "calendar_id": cal_id,
        "calendar_id_configured": "your_email" not in cal_id,
        "timezone": APP_TIMEZONE,
        "briefing_schedule": f"{BRIEFING_HOUR:02d}:{BRIEFING_MINUTE:02d} {APP_TIMEZONE}",
        "auth_required": bool(API_AUTH_TOKEN),
    }


def startup_report() -> None:
    """Prints the live/simulated summary once, when the server boots."""
    cal_id = gcal_config()["calendar_id"]
    backend = calendar_backend()

    print("=" * 66, flush=True)
    print("  AI Executive Assistant", flush=True)
    print(
        f"  Gemini      : {'configured' if gemini_configured() else 'MISSING API KEY'}",
        flush=True,
    )
    print(
        f"  Model       : {MODEL_NAME} (fallbacks: {', '.join(FALLBACK_MODELS) or 'none'})",
        flush=True,
    )
    print(f"  Timezone    : {APP_TIMEZONE}", flush=True)
    print(
        f"  Email       : {'Gmail SMTP' if smtp_configured() else 'SIMULATION only (set SMTP_APP_PASSWORD)'}",
        flush=True,
    )

    if backend == "none":
        print("  Calendar    : LOCAL ONLY (no usable credentials)", flush=True)
        print("                service account: python backend/google_auth.py", flush=True)
    else:
        print(f"  Calendar    : {backend.upper().replace('_', ' ')} -> {cal_id}", flush=True)
        if "your_email" in cal_id:
            print("                WARNING: GOOGLE_CALENDAR_ID is still a placeholder", flush=True)

    if CALENDAR_BACKEND == "oauth" and not oauth_token_present():
        print("                WARNING: CALENDAR_BACKEND=oauth but token.json is missing", flush=True)
        print("                run: python backend/google_oauth.py", flush=True)

    print(
        f"  Backend mode: CALENDAR_BACKEND={CALENDAR_BACKEND} "
        f"(oauth token: {'yes' if oauth_token_present() else 'no'}, "
        f"service key: {'yes' if service_key_present() else 'no'})",
        flush=True,
    )
    print(
        f"  Briefing    : {BRIEFING_HOUR:02d}:{BRIEFING_MINUTE:02d} {APP_TIMEZONE} "
        f"-> {', '.join(briefing_recipients())}",
        flush=True,
    )
    print(f"  Demo seed   : {'enabled' if SEED_DEMO_DATA else 'disabled'}", flush=True)
    print(
        f"  API auth    : {'X-API-Key required' if API_AUTH_TOKEN else 'open (local dev)'}",
        flush=True,
    )
    print("=" * 66, flush=True)
