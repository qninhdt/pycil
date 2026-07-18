"""Domain error types + FastAPI exception handlers.

Domains raise these; handlers translate to JSON responses so route code stays
free of HTTP plumbing.
"""

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


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


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": {},
                "requestId": getattr(request.state, "request_id", None),
            }
        },
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "details": {"errors": exc.errors()},
                "requestId": getattr(request.state, "request_id", None),
            }
        },
    )


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    codes = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": codes.get(exc.status_code, "http_error"),
                "message": str(exc.detail),
                "details": {},
                "requestId": getattr(request.state, "request_id", None),
            }
        },
    )
