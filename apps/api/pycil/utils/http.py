"""HTTP protocol helpers, status phrases, and transient error detection."""

from http import HTTPStatus

STANDARD_HTTP_METHODS: frozenset[str] = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "CONNECT", "TRACE"}
)


def http_status_phrase(status: int) -> str:
    """Return standard HTTP status phrase or fallback to 'Error'."""
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def normalize_http_method(method: str) -> str:
    """Normalize HTTP method against RFC standard methods, returning '_OTHER' if unknown."""
    return method if method in STANDARD_HTTP_METHODS else "_OTHER"


def is_transient_http_status(status: int | None) -> bool:
    """Check if an HTTP status code represents a transient, retryable error."""
    if not isinstance(status, int) or isinstance(status, bool):
        return False
    return status in {408, 409, 429} or status >= 500
