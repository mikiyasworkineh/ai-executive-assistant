"""Small, dependency-free helpers shared by the tool modules."""

from urllib.parse import urlparse


def norm(text) -> str:
    """Normalises a title for comparisons (case, quotes, whitespace)."""
    cleaned = str(text or "").lower().replace("'", "").replace('"', "")
    return " ".join(cleaned.split())


def fmt_time(value) -> str:
    """Extracts HH:MM from '2026-11-27T11:00' or RFC3339 '...T11:00:00+03:00'."""
    text = str(value or "")
    if "T" in text:
        return text.split("T", 1)[1][:5]
    return text[-5:]


def looks_like_email(value: str) -> bool:
    """Cheap email sanity check (no network validation)."""
    value = (value or "").strip()
    if "@" not in value:
        return False
    domain = value.rsplit("@", 1)[-1]
    return "." in domain and " " not in value and bool(urlparse(f"//{domain}").netloc)


def split_emails(value: str) -> list[str]:
    """Splits 'a@x.com; b@y.com' into valid-looking addresses."""
    raw = str(value or "").replace(";", ",").split(",")
    return [item.strip() for item in raw if looks_like_email(item)]
