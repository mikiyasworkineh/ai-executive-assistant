"""The Gemini agent: system prompt + one orchestration run.

The model receives the user's text plus the tools from `app.tools.ALL_TOOLS`
and decides which functions to call. Function calling is automatic: the SDK
executes each tool, feeds the result back, and loops until the model answers
with text.
"""

from datetime import timedelta

from google.genai import types

from .config import (
    APP_TIMEZONE,
    MODEL_NAME,
    gemini_api_key,
    gemini_configured,
    now_local,
    today_local,
)
from .gemini_client import build_client, generate_with_fallback, is_retryable, response_text
from .tracing import current_trace, log_action, start_trace
from .tools import ALL_TOOLS

# Keep the tool-use rules short and imperative: they are the difference
# between "chat about a meeting" and "actually book it".
SYSTEM_PROMPT = """\
You are an autonomous AI Executive Assistant for a Tech Startup Founder.
Current Date & Time: {now} ({timezone})
Today's Date: {today}
Tomorrow's Date: {tomorrow}

Rules for tool execution:
1. Whenever a meeting or call needs to be scheduled, ALWAYS call
   `check_calendar_availability` for that date first, then call
   `book_calendar_meeting` using 'YYYY-MM-DDTHH:MM' format.
2. Whenever asked to email someone or send a follow-up/agenda, call
   `send_executive_email` with a polished, professional subject and body.
3. Whenever asked to add a NEW task/reminder or when meeting notes contain
   action items, call `add_executive_task` with priority
   ('Urgent', 'Normal', or 'Low') and due_date ('YYYY-MM-DD').
4. In 'notes' mode (Notes-to-Action), extract and execute ALL mentioned
   meetings, follow-up emails, and tasks in a single run.
5. When asked to mark a task done/complete/finished, or to reopen it, ALWAYS
   call `set_task_status` with the existing task title. NEVER call
   add_executive_task for that, and NEVER create a task whose title is an
   instruction such as "Mark X as complete".
6. When asked what the tasks are, or before changing one, call `list_tasks`
   first. Only report tasks it returns; never invent task titles.
7. Before cancelling or rescheduling a meeting, call `list_events` to find the
   real event, then use `cancel_event(title)` or
   `reschedule_event(title, new_start, new_end)`. NEVER cancel by booking a new
   event, never create titles like "CANCELLED: X", and never duplicate the
   meeting you were asked to remove.
8. Never claim an action succeeded unless a tool returned success. If no tool
   fits, say what you cannot do.
Finish with a clear summary of every action you completed.
"""


class AgentError(Exception):
    """Base error for the agent endpoint."""


class AgentNotConfigured(AgentError):
    """No Gemini API key in .env."""


class AgentOverloaded(AgentError):
    """Every model in the fallback chain returned a transient error."""


def build_system_prompt() -> str:
    tomorrow = (now_local() + timedelta(days=1)).strftime("%Y-%m-%d")
    return SYSTEM_PROMPT.format(
        now=now_local().strftime("%Y-%m-%d %H:%M"),
        timezone=APP_TIMEZONE,
        today=today_local(),
        tomorrow=tomorrow,
    )


def run_agent(prompt: str, mode: str = "command") -> dict:
    """Executes one user request and returns `{reply, trace}`."""
    start_trace()

    if not gemini_configured():
        raise AgentNotConfigured(
            "GEMINI_API_KEY is not set! Open backend/.env and paste your "
            "Google AI Studio API key."
        )

    log_action("Agent Started", f"Analyzing {mode.upper()} request with {MODEL_NAME}...")

    try:
        client = build_client(gemini_api_key())
        response, used_model = generate_with_fallback(
            client,
            prompt=prompt,
            config=types.GenerateContentConfig(
                system_instruction=build_system_prompt(),
                tools=ALL_TOOLS,
                temperature=0.2,
            ),
        )
        reply = response_text(response, "All requested executive actions have been executed.")
        log_action("Workflow Complete", f"Finished executing all tool calls ({used_model}).")
        return {"reply": reply, "trace": current_trace()}
    except Exception as error:  # noqa: BLE001 - translated for the HTTP layer
        log_action("Agent Error", str(error)[:300])
        if is_retryable(error):
            raise AgentOverloaded(
                "Gemini is temporarily overloaded (503/504) and every model in the "
                "fallback chain is busy. Please retry in a few seconds."
            ) from error
        raise
