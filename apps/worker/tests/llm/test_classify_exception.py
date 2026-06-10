"""Unit tests for `classify_exception` — the retryable/terminal taxonomy.

Pure logic, no I/O. Pins the contract the fallback chain depends on:
- HTTP status in the retryable set → retryable (hops to next model).
- Other 4xx status → terminal (real bug, surface immediately).
- Exception class name match → retryable or terminal per the name lists.
- Message-substring fallback (rate limit / timeout / overloaded) → retryable.
- Anything unidentifiable → terminal (don't churn the chain on mystery errors).
"""
from __future__ import annotations

import pytest

from worker.llm.exceptions import (
    OpenRouterRetryableError,
    OpenRouterTerminalError,
    classify_exception,
)


class _StatusExc(Exception):
    """Carries a `status_code` like httpx/openai HTTP errors."""

    def __init__(self, status_code: int, msg: str = "") -> None:
        super().__init__(msg)
        self.status_code = status_code


class _ResponseExc(Exception):
    """Carries status via a nested `response.status_code` (httpx style)."""

    def __init__(self, status_code: int, msg: str = "") -> None:
        super().__init__(msg)

        class _Resp:
            def __init__(self, code: int) -> None:
                self.status_code = code

        self.response = _Resp(status_code)


@pytest.mark.unit
@pytest.mark.parametrize("status", [408, 409, 425, 429, 500, 502, 503, 504, 522, 524])
def test_retryable_status_codes(status: int) -> None:
    assert classify_exception(_StatusExc(status)) is OpenRouterRetryableError


@pytest.mark.unit
@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_other_4xx_is_terminal(status: int) -> None:
    assert classify_exception(_StatusExc(status)) is OpenRouterTerminalError


@pytest.mark.unit
def test_status_via_nested_response(status: int = 503) -> None:
    assert classify_exception(_ResponseExc(status)) is OpenRouterRetryableError


@pytest.mark.unit
@pytest.mark.parametrize(
    "name",
    [
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
    ],
)
def test_retryable_by_class_name(name: str) -> None:
    exc = type(name, (Exception,), {})()
    assert classify_exception(exc) is OpenRouterRetryableError


@pytest.mark.unit
@pytest.mark.parametrize(
    "name",
    [
        "BadRequestError",
        "AuthenticationError",
        "PermissionDeniedError",
        "NotFoundError",
        "UnprocessableEntityError",
        "ValidationError",
    ],
)
def test_terminal_by_class_name(name: str) -> None:
    exc = type(name, (Exception,), {})()
    assert classify_exception(exc) is OpenRouterTerminalError


@pytest.mark.unit
@pytest.mark.parametrize(
    "msg",
    ["rate limit hit", "Rate Limit exceeded", "request timeout", "model overloaded"],
)
def test_retryable_by_message_substring(msg: str) -> None:
    assert classify_exception(Exception(msg)) is OpenRouterRetryableError


@pytest.mark.unit
def test_unknown_exception_is_terminal() -> None:
    assert classify_exception(Exception("something nobody anticipated")) is (
        OpenRouterTerminalError
    )


@pytest.mark.unit
def test_status_code_wins_over_name() -> None:
    # A 429 on a class whose name isn't in either list must still be retryable.
    exc = _StatusExc(429, "weird")
    exc.__class__.__name__ = "SomethingWeird"
    assert classify_exception(exc) is OpenRouterRetryableError
