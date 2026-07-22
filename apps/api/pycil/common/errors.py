"""Domain error types + FastAPI exception handlers.

Domains raise these; handlers translate to JSON responses so route code stays
free of HTTP plumbing.
"""

from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    """The stable, client-facing shape carried by every API error."""

    model_config = ConfigDict(populate_by_name=True)

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = Field(default=None, alias="requestId")


class ErrorEnvelope(BaseModel):
    """Canonical non-success response body for the public API."""

    error: ErrorDetail


def error_responses(*status_codes: int) -> dict[int, dict[str, Any]]:
    """OpenAPI response metadata that mirrors the runtime error envelope."""
    return {
        status_code: {"model": ErrorEnvelope, "description": "Canonical API error."}
        for status_code in status_codes
    }


class AppError(Exception):
    status_code: int = 400
    code: str = "bad_request"

    def __init__(self, message: str, *, code: str | None = None):
        self.message = message
        if code:
            self.code = code
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
    request: Request, *, code: str, message: str, details: dict[str, Any] | None = None
) -> ErrorEnvelope:
    return ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            message=message,
            details=details or {},
            request_id=getattr(request.state, "request_id", None),
        )
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    headers = {}
    if isinstance(exc, TooManyRequestsError) and exc.retry_after is not None:
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(request, code=exc.code, message=exc.message).model_dump(
            by_alias=True
        ),
        headers=headers,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_envelope(
            request,
            code="validation_error",
            message="Request validation failed",
            details={"errors": exc.errors()},
        ).model_dump(by_alias=True),
    )


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    codes = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(
            request, code=codes.get(exc.status_code, "http_error"), message=str(exc.detail)
        ).model_dump(by_alias=True),
    )
