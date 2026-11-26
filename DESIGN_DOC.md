# Design Document — AI Executive Assistant

Status: implemented · Last updated: 2026-11-26 · Repo: `ai-executive-assistant`

---

## 1. Problem

A startup founder's work is spread across three tools that don't talk to each
other: **calendar**, **inbox**, **task list**. Every request repeats the same
manual loop:

```
read the request → check availability → create the event → write the follow-up
→ remember the action item
```

That loop costs hours per week and still produces double bookings, dropped
follow-ups and action items that only exist in someone's head.

Most "AI assistants" stop at *drafting text* — the user still has to execute.
This project optimises for the opposite: **the agent performs the actions and
proves it did**.

## 2. Goals and non-goals

**Goals**

1. One sentence in → real calendar event, real email, real task, with a visible
   step-by-step trace.
2. Never double-book: availability is checked against the *live* calendar.
3. Multi-step work in one run (meeting notes → booking + email + tasks).
4. Proactive value without prompting (daily briefing email).
5. Trust: no fake successes, no duplicate writes, ask when unsure.

**Non-goals**

- Multi-user accounts, team calendars, shared boards.
- Reading/triaging the inbox (compose + send only).
- Recurring events, conference links, attachments.
- Financial/HR actions; anything with a destructive blast radius.

## 3. Role and interaction model

**Role:** autonomous executive assistant for one founder.

**Interaction:** a single page with two input modes.

| Mode | Input | Intent |
|---|---|---|
| Smart Command | one instruction | perform one (or a few) actions |
| Notes-to-Action | pasted meeting notes | extract **all** actions and execute them |

The UI is deliberately thin: it posts a prompt, renders the reply, and renders
the returned trace. All decisions happen server-side, so the same behaviour is
available from the API.

## 4. Architecture

```
Next.js page ──HTTP──► FastAPI
                         ├─ agent.py     system prompt + 9 tools
                         ├─ tools/*      validation + side effects
                         ├─ calendar_api Google credentials / CRUD
                         ├─ briefing.py  daily email
                         └─ SQLite       mirror + logs
                                │
                    ┌───────────┴────────────┐
              Google Gemini            Google Calendar / Gmail
```

**Key principle: the LLM plans, the backend executes.** Gemini receives typed
Python functions with docstrings and returns function calls; the backend runs
them, appends each result to a trace, and loops until the model answers with
text. Credentials never reach the model.

### 4.1 Backend modules

| Module | Responsibility |
|---|---|
| `config.py` | single source of truth for `.env`, timezone helpers, readiness flags |
| `database.py` | schema (`tasks`, `calendar_events`, `emails`, `action_logs`), demo seeding |
| `tracing.py` | per-request `ContextVar` trace + persisted activity log |
| `gemini_client.py` | client, timeout, retries, model fallback, safe text extraction |
| `calendar_api.py` | service-account/OAuth clients, live reads, insert/delete/patch, app tagging |
| `tools/calendar.py` | availability, event list, conflict resolution, cancel, reschedule |
| `tools/email.py` | Gmail SMTP delivery + truthful status logging |
| `tools/tasks.py` | list/add/status with fuzzy matching and guards |
| `agent.py` | system prompt (tool rules) + orchestration |
| `briefing.py` | schedule audit + narrative + send |
| `scheduler.py` | APScheduler cron at `BRIEFING_HOUR:BRIEFING_MINUTE` |
| `routes.py` | HTTP endpoints; maps domain errors to 400/503/500 |
| `security.py` | optional `X-API-Key` guard |
| `diagnostics.py` | startup banner + `/api/health` |
| `application.py` | FastAPI factory, CORS, lifespan |

### 4.2 Data model

```
tasks            id, title, priority(Urgent|Normal|Low), due_date, status, created_at
calendar_events  id, gcal_id, title, start_time, end_time, attendees, description, source
emails           id, recipient, subject, body, status, sent_at
action_logs      id, step_type, message, timestamp
```

`calendar_events` is a **mirror**: Google Calendar stays the source of truth and
is read live for availability, conflicts and the briefing.

## 5. Design decisions

### D1 — Function calling instead of prompt parsing

The model chooses tools; the backend owns validation and effects. Adding a
capability is: write a typed function, add it to `ALL_TOOLS`, mention it in the
prompt rules. No brittle regex parsing of model output.

### D2 — Conflict-aware booking

Availability merges the local mirror with **live** Google events, so meetings
created outside the app still block slots. On overlap the meeting is pushed to
the next free slot (max 6 attempts) instead of failing or double-booking.

### D3 — Tasks and events are separate concepts

Events block time; tasks have a due date and priority but never occupy the
calendar. This matches how founders actually think and keeps conflict logic
meaningful.

### D4 — Truthful statuses

Emails record `Delivered via Gmail SMTP`, `SMTP failed: …` or
`Simulated (SMTP not configured)`. Bookings state whether Google sync happened.
Briefings always end with the raw schedule/task audit so the model cannot
paraphrase a meeting away. Trust is a feature.

### D5 — Credential strategy

| Mode | Use | Limitation |
|---|---|---|
| Service account (default) | zero-interaction server auth; calendar shared with the SA email | Google forbids inviting attendees |
| OAuth (optional) | acts as the user, sends real guest invites | one-time browser consent |

Chosen as *defaults, not switches*: `CALENDAR_BACKEND=auto` prefers OAuth when a
token exists. When a service account is blocked from inviting, the event is still
created, the guest is recorded in the description, and the trace says so.

### D6 — Model strategy

```
primary   gemini-3.1-flash-lite        fast, usually available, cheap
fallback  gemini-3.8-flash             stronger reasoning if the primary fails
fallback  gemini-flash-latest          last resort alias
```

Google frequently returns `503 UNAVAILABLE` on the newest aliases; a lite model
is more available and its latency suits short tool-driven turns. The trade-off
is weaker multi-step reasoning, so the retry/fallback chain and deterministic
guards carry the reliability burden instead of model quality alone.
`GEMINI_ATTEMPTS`, `GEMINI_REQUEST_TIMEOUT_MS` and `GEMINI_MAX_SECONDS` bound the
worst case; the SDK's own retries are disabled so latency is controlled here.

### D7 — Safety nets around a probabilistic core

| Risk | Mitigation |
|---|---|
| Duplicate tasks | title match across all statuses → skip |
| "Mark X done" creating a task | instruction-prefix + existing-title detection → refuse, point to `set_task_status` |
| "Remove meeting" booking a `CANCELLED:` event | cancellation-marker and instruction-title refusal in `book_calendar_meeting` |
| Wrong record changed | fuzzy match; 0 matches → explain, >1 → ask |
| Hallucinated lists | read tools (`list_tasks`, `list_events`) must be used before reporting |
| Fake success | system rule: never claim success without a tool result |

### D8 — Observability

Each request starts a trace in a `ContextVar` (safe under concurrency), every
tool appends a step, and the same step is persisted to `action_logs`. The UI
renders the live trace; `/api/health` reports which integrations are live.

### D9 — Demo operability

- `SEED_DEMO_DATA` seeds a realistic board on an empty install.
- `backend/reset_demo.py` / `POST /api/demo/reset` / the **Reset demo** button
  clear local tables and optionally reseed, for repeatable recordings.
- Events created by the app carry `extendedProperties.private.source =
  ai-executive-assistant`, so Google cleanup still works after the local mirror
  is wiped.

## 6. Error handling

| Situation | Behaviour |
|---|---|
| Gemini 503/429/504 | retry → next model → clear 503 message |
| No API key | 400 with setup instructions |
| No calendar credentials | local-only mode; replies say sync is not configured |
| Google invite refused | create without attendees + note + trace entry |
| SMTP missing/failing | stored as simulated/failed; never reported as sent |
| Invalid dates/titles | logged `Conflict Check Skipped` / booking refused; nothing silently written |
| Ambiguity | no write, asks which record |

## 7. Security

- Secrets only in `backend/.env` (gitignored); `.env.example` documents keys.
- Optional `API_AUTH_TOKEN` → `X-API-Key` on all mutating endpoints.
- CORS restricted by `ALLOWED_ORIGINS` (wildcard + credentials not used).
- Least privilege: one shared calendar; revocable Gmail app password.
- Audit trail: `action_logs` + per-request trace.

## 8. Verification performed

| Scenario | Outcome |
|---|---|
| Book over a live Google event | shifted 09:00 → 09:30, present in Google, mirror consistent |
| Notes with 4 actions | booking + email + 2 tasks in one trace |
| "Mark X complete" | status updated, no new task |
| "Remove event" | deleted from Google + mirror, no `CANCELLED:` placeholder |
| Morning briefing | email delivered, includes live events + tasks |
| Reset demo + reseed | 0 → 2 events / 2 tasks, Google untouched |
| Model switch to 3.1-flash-lite | 5.2 s tool call, no fallback hop |

## 9. Known limitations

- Single user, single calendar, one SQLite file.
- Scheduler lives in the API process: the 08:00 email only fires while the
  server runs (use Task Scheduler / Cloud Scheduler against the endpoint).
- Runs are not transactional: a mid-run failure can leave earlier actions
  applied; the trace shows exactly what happened.
- No plan-confirmation step before writes (mitigated by guards).
- API auth is off by default for local development.

## 10. Future work

1. Plan preview + explicit confirmation before bookings/emails.
2. Multi-user OAuth, Postgres, per-user calendars and boards.
3. Inbox read/triage and reply drafting.
4. Recurring events, conference links, attachments.
5. Persistent scheduler, run history, duplicate-send guard for briefings.
6. CI evaluation harness replaying a fixed prompt suite.
