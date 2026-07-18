"""HTTP middleware: body-size cap, CORS, security headers, internal-secret guard.

The internal-secret guard protects worker→api callback routes (prefix
``/internal``). It compares in constant time and rejects empty/missing secrets so
a blank env var can never open the gate.
"""

import hmac
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from pycil.config import settings

INTERNAL_PREFIX = "/internal"


def _request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if request_id is None:
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        request.state.request_id = request_id
    return request_id


def _middleware_error(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    response = JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": {},
                "requestId": _request_id(request),
            }
        },
    )
    response.headers["X-Request-ID"] = _request_id(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl is not None and cl.isdigit() and int(cl) > self.max_bytes:
            return _middleware_error(request, 413, "payload_too_large", "Body too large")
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach an opaque correlation id to every response and error envelope."""

    async def dispatch(self, request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or uuid4().hex
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response


class InternalSecretMiddleware(BaseHTTPMiddleware):
    """Constant-time guard on /internal/* routes; empty/missing secret rejected."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(INTERNAL_PREFIX):
            presented = request.headers.get("X-Internal-Secret", "")
            expected = settings.internal_secret
            if not presented or not expected or not hmac.compare_digest(presented, expected):
                return _middleware_error(request, 401, "unauthorized", "Bad internal secret")
        return await call_next(request)


def install_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(InternalSecretMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_body_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
