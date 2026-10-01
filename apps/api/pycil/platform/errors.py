"""Domain error types + FastAPI exception handlers.

Domains raise these; handlers translate to JSON responses so route code stays
free of HTTP plumbing.
"""

import logging
import re
from http import HTTPStatus
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

# A message that is itself a machine-readable identifier: lowercase words joined
# by single underscores. Human prose fails this — it has spaces, punctuation, or
# interpolated values.
_CODE_SHAPED = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")

logger = logging.getLogger(__name__)


class ProblemDetails(BaseModel):
    """RFC 9457 problem document with Pycil's stable domain-code extension."""

    model_config = ConfigDict(populate_by_name=True)

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str | None = None
    code: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = Field(default=None, alias="requestId")


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI response metadata that mirrors the runtime problem document."""
    return {
        status_code: {
            "description": "RFC 9457 Problem Details response.",
            "content": {"application/problem+json": {"schema": ProblemDetails.model_json_schema()}},
        }
        for status_code in status_codes
    }


class AppError(Exception):
    """A domain failure, carrying the identifier a client branches on.

    Almost every raise site in this codebase passes a snake_case identifier as
    the only argument — `ConflictError("session_scope_changed")`. Treating that
    purely as a human message left the wire `code` at the class default, so four
    distinct conflicts all arrived as `conflict`: a client could see that
    something conflicted but not whether to abandon the session, retry the same
    question, or move to a different one. The identifier the raise site already
    supplies is the specific answer, so it becomes the code.

    Prose messages are left alone. They are not identifiers and must not be
    presented to a client as something to branch on.
    """

    status_code: int = 400
    code: str = "bad_request"

    def __init__(self, message: str, *, code: str | None = None):
        self.message = message
        if code:
            self.code = code
        elif _CODE_SHAPED.fullmatch(message):
            self.code = message
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class PayloadTooLargeError(AppError):
    """A request body field exceeds a declared size limit."""

    status_code = 413
    code = "payload_too_large"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"


class TooManyRequestsError(AppError):
    """Rate-limit rejection, optionally telling the client when to retry."""

    status_code = 429
    code = "too_many_requests"

    def __init__(
        self,
        message: str = "Too many requests",
        *,
        retry_after: int | None = None,
        code: str | None = None,
    ):
        self.retry_after = retry_after
        super().__init__(message, code=code)


def error_envelope(
    request: Request,
    *,
    status: int = 400,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> ProblemDetails:
    """Build the public problem document."""
    try:
        title = HTTPStatus(status).phrase
    except ValueError:
        title = "HTTP error"
    return ProblemDetails(
        title=title,
        status=status,
        detail=message,
        instance=request.url.path,
        code=code,
        details=details or {},
        request_id=getattr(request.state, "request_id", None),
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    headers = {}
    if isinstance(exc, TooManyRequestsError) and exc.retry_after is not None:
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(
            request, status=exc.status_code, code=exc.code, message=exc.message
        ).model_dump(by_alias=True, exclude_none=True),
        media_type="application/problem+json",
        headers=headers,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    safe_errors = [
        {key: value for key, value in error.items() if key not in {"input", "ctx"}}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=error_envelope(
            request,
            status=422,
            code="validation_error",
            message="Request validation failed",
            details={"errors": safe_errors},
        ).model_dump(by_alias=True, exclude_none=True),
        media_type="application/problem+json",
    )


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    codes = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(
            request,
            status=exc.status_code,
            code=codes.get(exc.status_code, "http_error"),
            message=str(exc.detail),
        ).model_dump(by_alias=True, exclude_none=True),
        media_type="application/problem+json",
        headers=exc.headers,
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last resort: an exception nothing else claimed still leaves as an envelope.

    Without this, an unexpected type falls through to Starlette's default and the
    client receives a bare `Internal Server Error` — no `code`, no `requestId`,
    and not the JSON shape its error parser expects. The web taxonomy keys off
    `error.code`, so such a response is unparseable rather than merely untidy, and
    surfaces to the user as a network failure instead of a server error.

    The exception's own message is deliberately NOT returned. It was written by
    whichever library raised it and can carry a connection string, a query, or a
    row of user data; the caller can do nothing with it either way. It is logged
    with the request id so the two can be matched.
    """
    logger.exception(
        "unhandled exception",
        extra={"request_id": getattr(request.state, "request_id", None)},
    )
    return JSONResponse(
        status_code=500,
        content=error_envelope(
            request,
            status=500,
            code="internal_error",
            message="An unexpected error occurred.",
        ).model_dump(by_alias=True, exclude_none=True),
        media_type="application/problem+json",
    )
