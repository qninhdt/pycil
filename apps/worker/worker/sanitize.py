"""LLM output sanitization. Strip URLs, HTML tags, control chars."""
from __future__ import annotations

import re

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w{2,}\b")
_HTML_RE = re.compile(r"<[^>]+>")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_text(value: str) -> str:
    """Strip URLs/emails/HTML/control chars; collapse whitespace."""
    if not value:
        return value
    cleaned = _URL_RE.sub("", value)
    cleaned = _EMAIL_RE.sub("", cleaned)
    cleaned = _HTML_RE.sub("", cleaned)
    cleaned = _CONTROL_RE.sub("", cleaned)
    return " ".join(cleaned.split())


def sanitize_list(values: list[str]) -> list[str]:
    return [s for s in (sanitize_text(v) for v in values) if s]
