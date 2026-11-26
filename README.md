# AI Executive Assistant

An autonomous executive assistant for a startup founder. Instead of a chat bot
that *describes* what it would do, it **actually does it**: books conflict-free
meetings on Google Calendar, sends follow-up emails over Gmail, and manages a
prioritised task board - all driven by natural language through Gemini function
calling.

```
You:  "Book a 30-min roadmap sync with alex@company.com tomorrow at 15:00,
       check conflicts first, email him the agenda, and add an urgent task
       to review the Q4 budget."

Agent: check_calendar_availability -> book_calendar_meeting (auto-shifts on
       conflict) -> send_executive_email -> add_executive_task
       Reply: "14:00 was busy, so I booked 15:30-16:00, emailed the agenda,
       and added the Urgent task."
```

## Contents

- [Problem](#problem)
- [Features](#features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Quickstart](#quickstart)
- [Configuration](#configuration)
- [Agent tools](#agent-tools)
- [HTTP API](#http-api)
- [Data model](#data-model)
- [Design decisions](#design-decisions)
- [Known limitations](#known-limitations)
- [Repository layout](#repository-layout)

## Problem

A founder's day is fragmented across three tools that do not talk to each
other: calendar, inbox, and a to-do list. The manual loop is expensive -
reading a meeting request, checking availability, creating the event, writing a
follow-up email, and remembering the action items. Each step is simple, but
together they consume hours per week and cause double bookings and dropped
follow-ups.

The goal was a single interface that turns one sentence (or a page of messy
meeting notes) into completed, verified actions in the tools the founder
already uses.

## Features

| Feature | What it does |
|---|---|
| **Conflict-aware scheduling** | Reads local + live Google Calendar events, detects overlaps, auto-shifts the requested slot to the next free gap, then writes the event to Google Calendar |
| **Executive email drafting & sending** | Gemini writes the subject/body, the backend sends it over Gmail SMTP and records a *truthful* delivery status |
| **Notes-to-action** | Paste raw meeting notes; the agent extracts and executes every meeting, email and task in one run |
| **Task extraction & priority triage** | `Urgent` / `Normal` / `Low` with due dates, duplicate protection, fuzzy title matching, status updates ("mark X done") |
| **Proactive morning briefing** | A daily 08:00 job audits today's schedule + pending tasks, writes a briefing and emails it; also exposed as an HTTP endpoint for external cron |
| **Live execution trace** | Every tool call is streamed back to the UI and persisted to an activity log |

## Architecture

```
                    ┌──────────────────────────────┐
   Browser          │  Next.js 16 (React 19)       │
   localhost:3000   │  app/page.tsx                │
                    │  - command / notes box       │
                    │  - live execution trace      │
                    │  - calendar · tasks · emails │
                    └──────────────┬───────────────┘
                                   │ JSON over HTTP
                    ┌──────────────▼───────────────┐
                    │  FastAPI  (backend/app)      │
                    │  routes.py -> agent.py       │
                    │  system prompt + 9 tools     │
                    └──────┬───────────┬───────────┘
                           │           │ function calling
                ┌──────────▼───┐   ┌───▼──────────────────┐
                │  Gemini      │   │  Tool layer          │
                │  retry +     │   │  calendar / email /  │
                │  model       │   │  tasks               │
                │  fallback    │   └───┬──────────┬───────┘
                └──────────────┘       │          │
                              ┌────────▼──┐   ┌───▼─────────┐
                              │ Google    │   │ Gmail SMTP  │
                              │ Calendar  │   │             │
                              └───────────┘   └─────────────┘
                                       │
                              ┌────────▼─────────┐
                              │ SQLite mirror    │
                              │ tasks, events,   │
                              │ emails, logs     │
                              └──────────────────┘
```

One request: `POST /api/agent/execute` -> `agent.run_agent` -> Gemini with the
tool registry -> automatic function calling loop -> tools write to Google
Calendar / Gmail / SQLite -> trace returned to the UI.

## Tech stack

- **Backend:** Python 3.12, FastAPI, Pydantic, SQLite, APScheduler
- **AI:** Google Gemini via `google-genai` (function calling, retry + model fallback)
- **Integrations:** Google Calendar API (service account or OAuth), Gmail SMTP
- **Frontend:** Next.js 16, React 19, TypeScript, Tailwind CSS 4, lucide-react

## Quickstart

Requirements: Python 3.11+, Node 20+, a Gemini API key.

```bash
# 1. Backend
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r backend/requirements.txt
copy backend\.env.example backend\.env    # then edit it
run-backend.bat                    # http://localhost:8000

# 2. Frontend (second terminal)
cd frontend
npm install
npm run dev                        # http://localhost:3000
```

Open <http://localhost:3000>, click **Demo Conflict Command**, then
**Execute Assistant Command**.

### Integration setup

| Integration | Steps | Verification |
|---|---|---|
| Gemini (required) | paste a key from <https://aistudio.google.com/> into `GEMINI_API_KEY` | `GET /api/health` -> `gemini_api_key_configured: true` |
| Google Calendar | create a service account, enable Calendar API, download the JSON to `backend/service_account.json`, share the target calendar with the service-account email ("Make changes to events") | `python backend/google_auth.py` |
| Guest invites (optional) | OAuth desktop client -> `backend/credentials.json`, then `python backend/google_oauth.py` | `calendar_backend: "oauth"` |
| Gmail sending | enable 2-Step Verification, create an App Password, set `SMTP_EMAIL` + `SMTP_APP_PASSWORD` | send a test email from the UI |

Without calendar credentials the app still works, using the local SQLite
mirror only. Without SMTP credentials emails are recorded as
`Simulated (SMTP not configured)` instead of pretending they were delivered.

## Configuration

All settings live in `backend/.env` (template: `backend/.env.example`).

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | - | required |
| `GEMINI_MODEL` | `gemini-flash-latest` | primary model |
| `GEMINI_FALLBACK_MODELS` | `gemini-3.8-flash,gemini-3.1-flash-lite` | tried in order on 503/429 |
| `APP_TIMEZONE` | `UTC` | timezone for events, briefing, display |
| `GOOGLE_CALENDAR_ID` | `primary` | target calendar |
| `CALENDAR_BACKEND` | `auto` | `auto` / `service_account` / `oauth` |
| `SERVICE_ACCOUNT_FILE` | `service_account.json` | service-account key |
| `SMTP_EMAIL`, `SMTP_APP_PASSWORD` | - | Gmail sender + app password |
| `EXECUTIVE_EMAIL`, `BRIEFING_RECIPIENTS` | - | briefing recipients |
| `BRIEFING_HOUR`, `BRIEFING_MINUTE` | `8`, `0` | daily briefing time |
| `API_AUTH_TOKEN` | empty | when set, `POST`/`DELETE` need `X-API-Key` |
| `ALLOWED_ORIGINS` | `*` | CORS allow-list |
| `SEED_DEMO_DATA` | `true` | seed fake meetings/tasks on an empty DB |

## Agent tools

The model chooses from nine typed Python functions (see
`backend/app/tools/`). Adding a tool is one function + one list entry.

| Tool | Side effect |
|---|---|
| `check_calendar_availability(date)` | read: busy slots for one day (local + live Google) |
| `list_events(date, days)` | read: scheduled events with attendees |
| `book_calendar_meeting(title, start, end, attendee, description)` | conflict check, auto-shift, Google Calendar insert, local mirror |
| `cancel_event(title, date)` | delete from Google Calendar + local mirror |
| `reschedule_event(title, new_start, new_end, date)` | move in Google Calendar + local mirror (conflict-aware) |
| `send_executive_email(to, subject, body)` | Gmail SMTP send + delivery log |
| `list_tasks(status)` | read: tasks with priority/due/status |
| `add_executive_task(title, priority, due_date)` | new task, duplicate + meta-instruction guard |
| `set_task_status(title, status)` | mark complete / reopen (fuzzy title match) |

Safety guards: the agent cannot create a task whose title is an instruction
("Mark X as complete"), cannot book events titled `CANCELLED: ...`, and asks
for clarification when a title matches several records.

## HTTP API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/agent/execute` | run the assistant: `{prompt, mode}` -> `{reply, trace}` |
| `POST` | `/api/cron/morning-briefing` | trigger the daily briefing (external cron) |
| `GET` | `/api/health` | which integrations are live vs simulated |
| `GET` | `/api/dashboard` | events + tasks + emails + activity log |
| `POST` | `/api/tasks/{id}/toggle` | pending <-> completed |
| `DELETE` | `/api/tasks/{id}` | delete a task |

`mode` is a hint: `command` (single request) or `notes` (extract every action
from pasted notes). Interactive docs at `http://localhost:8000/docs`.

## Data model

```
tasks            id, title, priority, due_date, status, created_at
calendar_events  id, gcal_id, title, start_time, end_time, attendees, description, source
emails           id, recipient, subject, body, status, sent_at
action_logs      id, step_type, message, timestamp
```

`calendar_events` is a local mirror; Google Calendar remains the source of
truth and is read live for availability, conflict checks and the briefing.

## Design decisions

- **Function calling, not prompt parsing.** The model decides which tool to run
  and with which arguments; the tool layer owns validation and side effects.
- **Retry + fallback for Gemini.** 503s are common on new models; the client
  retries briefly and then walks a fallback list, with a bounded time budget.
- **Truthful statuses.** Emails record `Delivered via Gmail SMTP`,
  `SMTP failed: ...` or `Simulated (SMTP not configured)` - never a fake
  success. Bookings say whether Google sync actually happened.
- **Service-account limitation handled.** Google forbids service accounts from
  inviting attendees; the event is still created and the guest is noted in the
  description, with OAuth available as an opt-in upgrade.
- **Deterministic safety nets.** Duplicate/meta-task guards, cancellation-title
  guards, ambiguity prompts, and an authoritative schedule audit appended to
  every briefing so the model cannot paraphrase a meeting away.
- **Clean layering.** `config` / `database` / `tracing` / `gemini_client` /
  `calendar_api` / `tools` / `agent` / `routes` / `scheduler` - the HTTP layer
  is thin, business logic is testable in isolation.

## Known limitations

- The scheduler runs inside the API process, so the 08:00 briefing only fires
  while the server is up (use Task Scheduler/Cloud Scheduler on a real host).
- No user accounts: one founder, one calendar, one task board.
- SQLite and in-memory traces suit a single-user local deployment.
- The agent is not transactional: a mid-run failure can leave earlier actions
  applied (the trace shows exactly what happened).
- `API_AUTH_TOKEN` is off by default for local development.

## Repository layout

```
ai-executive-assistant/
├── backend/
│   ├── main.py              uvicorn entrypoint (repo root or backend/)
│   ├── app/
│   │   ├── config.py        all .env settings, timezone helpers
│   │   ├── database.py      SQLite schema + demo seeding
│   │   ├── tracing.py       per-request trace + activity log
│   │   ├── gemini_client.py retries, model fallback
│   │   ├── calendar_api.py  Google credentials, live reads, insert/delete/patch
│   │   ├── tools/           calendar.py, email.py, tasks.py + registry
│   │   ├── agent.py         system prompt + orchestration
│   │   ├── briefing.py      morning briefing
│   │   ├── routes.py        HTTP endpoints
│   │   ├── scheduler.py     APScheduler cron
│   │   ├── diagnostics.py   startup banner + /api/health
│   │   ├── security.py      optional X-API-Key
│   │   └── application.py   FastAPI factory
│   ├── google_auth.py       service-account verification script
│   ├── google_oauth.py      optional OAuth setup (guest invites)
│   ├── requirements.txt
│   └── README.md            backend module guide
├── frontend/                Next.js dashboard
├── run-backend.bat
└── README.md                this file
```

## Documentation

- `backend/README.md` - module-by-module backend guide and data flow
- `docs/DEMO_SCRIPT.md` - 6-minute walkthrough script for the demo video
- `http://localhost:8000/docs` - generated OpenAPI reference
