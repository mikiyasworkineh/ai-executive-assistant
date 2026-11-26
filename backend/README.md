# Backend architecture

Small FastAPI app that turns prompts into real calendar/email/task actions via
Gemini function calling.

```
backend/
├── main.py                  entrypoint only (~28 lines) → builds the app
├── google_auth.py           service-account setup check  (python backend/google_auth.py)
├── google_oauth.py          optional OAuth setup for guest invites
├── .env / .env.example      configuration
├── executive_assistant.db   SQLite data (auto-created)
└── app/
    ├── config.py            every .env setting in one place + time helpers
    ├── database.py          SQLite schema, connections, demo seeding
    ├── tracing.py           per-request trace + activity log
    ├── utils.py             title normalisation, time formatting, email parsing
    ├── gemini_client.py     Gemini client, retries, model fallback
    ├── calendar_api.py      Google Calendar credentials, live reads, inserts
    ├── tools/
    │   ├── calendar.py      availability, list, book, cancel, reschedule
    │   ├── email.py         send_executive_email (Gmail SMTP + DB log)
    │   └── tasks.py         list_tasks, add_executive_task, set_task_status
    ├── agent.py             system prompt + one orchestration run
    ├── briefing.py          morning briefing composition and sending
    ├── routes.py            HTTP endpoints (thin: no business logic)
    ├── scheduler.py         in-process cron (08:00 briefing)
    ├── diagnostics.py       startup banner + /api/health payload
    ├── security.py          optional X-API-Key guard
    └── application.py       FastAPI factory (CORS, lifespan)
```

## Data flow of one request

```
POST /api/agent/execute          routes.execute_agent
  └─ agent.run_agent             system prompt + ALL_TOOLS
       └─ gemini_client.generate_with_fallback   retry / model fallback
            └─ tools/*            database + Google Calendar + Gmail
                 └─ tracing.log_action   → action_logs table + response trace
```

## Adding a tool

1. Write a plain function with type hints and a docstring in `app/tools/`.
2. Append it to `ALL_TOOLS` in `app/tools/__init__.py`.
3. Mention it in the rules block of `SYSTEM_PROMPT` (`app/agent.py`) so the
   model actually prefers it.

## Run

```bash
run-backend.bat                                  # from the repo root
# or
.venv\Scripts\activate
uvicorn backend.main:app --reload --port 8000     # repo root
cd backend && uvicorn main:app --reload           # backend dir (also works)
```

`GET /api/health` reports which integrations are real vs simulated.
