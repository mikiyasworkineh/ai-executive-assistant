"""Optional API-key protection.

The app is meant for one person on localhost, so auth is opt-in: set
`API_AUTH_TOKEN` in `.env` and every mutating endpoint will require the same
value in an `X-API-Key` header. Leave it empty and nothing is enforced.
"""

from fastapi import Header, HTTPException

from .config import API_AUTH_TOKEN


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """FastAPI dependency: rejects requests when a token is configured."""
    if API_AUTH_TOKEN and x_api_key != API_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header.")
