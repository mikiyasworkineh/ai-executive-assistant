"""Gemini client wrapper: retries, model fallback and safe text extraction.

Why the retry logic lives here: Google's newest models frequently answer
`503 UNAVAILABLE` ("high demand"), and the multi-model aliases (e.g.
`gemini-2.5-flash`) are retired over time. The agent therefore retries a
transient failure a couple of times and then walks a fallback list.
"""

import time

from google import genai
from google.genai import types

from .config import (
    FALLBACK_MODELS,
    GEMINI_ATTEMPTS,
    GEMINI_MAX_SECONDS,
    GEMINI_REQUEST_TIMEOUT_MS,
    MODEL_NAME,
    RETRYABLE_ERROR_HINTS,
)
from .tracing import log_action


def build_client(api_key: str) -> genai.Client:
    """Creates a Gemini client with a bounded request timeout."""
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            api_version="v1beta",
            timeout=GEMINI_REQUEST_TIMEOUT_MS,
            # One attempt only: our own retry/fallback logic decides how long
            # to wait, instead of the SDK stalling on an overloaded model.
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def is_retryable(error: Exception) -> bool:
    """Transient Google errors worth retrying (503/429/504, timeouts, ...)."""
    text = f"{type(error).__name__} {error}".lower()
    return any(hint in text for hint in RETRYABLE_ERROR_HINTS)


def generate_with_fallback(client, *, prompt: str, config=None, attempts: int | None = None):
    """Runs a chat completion, retrying transient errors across models.

    Returns `(response, model_name_used)`. Raises the last error if every
    model and attempt failed, or when the overall time budget is exhausted.
    """
    attempts = attempts or GEMINI_ATTEMPTS
    models = [MODEL_NAME] + [m for m in FALLBACK_MODELS if m != MODEL_NAME]
    deadline = time.time() + GEMINI_MAX_SECONDS
    last_error: Exception | None = None

    for model in models:
        for attempt in range(1, attempts + 1):
            if time.time() >= deadline:
                raise last_error or TimeoutError(
                    f"Gemini did not respond within {GEMINI_MAX_SECONDS}s."
                )
            try:
                chat = (
                    client.chats.create(model=model, config=config)
                    if config
                    else client.chats.create(model=model)
                )
                response = chat.send_message(prompt)
                if model != MODEL_NAME:
                    log_action("Model Fallback", f"Responded using fallback model '{model}'.")
                return response, model
            except Exception as error:  # noqa: BLE001 - inspect then re-raise
                last_error = error
                print(
                    f"[gemini] {model} attempt {attempt} failed: "
                    f"{type(error).__name__}: {str(error)[:200]}",
                    flush=True,
                )
                if not is_retryable(error) or attempt == attempts:
                    break
                time.sleep(min(2 ** (attempt - 1), 8))

    raise last_error  # type: ignore[misc]


def response_text(response, default: str = "") -> str:
    """response.text can raise when the reply has no text parts (tool calls)."""
    try:
        return response.text or default
    except Exception:
        return default
