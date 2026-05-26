"""Exception taxonomy for OpenRouter LLM calls.

Distinguish retryable errors (server overload, rate limit, network blip,
timeout) from terminal errors (bad request, auth failure, schema bug).
Only retryable errors trigger the fallback chain.
"""
from __future__ import annotations


class OpenRouterError(Exception):
    """Base for all OpenRouter classification errors."""


class OpenRouterRetryableError(OpenRouterError):
    """503/429/timeout/connection — try the next fallback model."""


class OpenRouterTerminalError(OpenRouterError):
    """400/401/422/schema-bug — surface immediately, do NOT fall back."""


class OpenRouterAllModelsFailedError(OpenRouterRetryableError):
    """Every model in the fallback chain returned a retryable error."""


_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 522, 524}


def classify_exception(exc: BaseException) -> type[OpenRouterError]:
    """Map raw httpx / openai / langchain exceptions to retryable/terminal.

    Anything we cannot identify is treated as terminal — better to surface
    a real bug than to silently churn through the fallback chain.
    """
    name = type(exc).__name__
    msg = str(exc).lower()
    status = _extract_status(exc)

    if status in _RETRYABLE_STATUS:
        return OpenRouterRetryableError
    if status is not None and 400 <= status < 500:
        return OpenRouterTerminalError

    if name in {
        "TimeoutError",
        "ReadTimeout",
        "ConnectTimeout",
        "WriteTimeout",
        "PoolTimeout",
        "ConnectError",
        "RemoteProtocolError",
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
        "RateLimitError",
        "ServiceUnavailableError",
    }:
        return OpenRouterRetryableError
    if name in {
        "BadRequestError",
        "AuthenticationError",
        "PermissionDeniedError",
        "NotFoundError",
        "UnprocessableEntityError",
        "ValidationError",
    }:
        return OpenRouterTerminalError

    if "rate" in msg and "limit" in msg:
        return OpenRouterRetryableError
    if "timeout" in msg or "overloaded" in msg:
        return OpenRouterRetryableError

    return OpenRouterTerminalError


def _extract_status(exc: BaseException) -> int | None:
    for attr in ("status_code", "http_status", "code"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
    response = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status
    return None
