"""AI Executive Assistant backend package.

Module map:

    config.py        all .env settings, timezone helpers
    database.py      SQLite schema + demo seeding
    tracing.py       per-request step trace and activity log
    utils.py         small text/time helpers
    gemini_client.py Gemini client with retries + model fallback
    calendar_api.py  Google Calendar credentials, live reads, event inserts
    tools/           the functions the agent can call
    briefing.py      morning briefing composition + sending
    agent.py         system prompt and one orchestration run
    routes.py        HTTP endpoints
    scheduler.py     in-process cron for the briefing
    diagnostics.py   startup banner and /api/health payload
    security.py      optional X-API-Key guard
    application.py   FastAPI factory
"""

from .application import create_app

__all__ = ["create_app"]
