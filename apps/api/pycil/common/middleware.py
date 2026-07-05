"""HTTP middleware: body-size cap, CORS, security headers, internal-secret guard.

The internal-secret guard protects worker→api callback routes (prefix
``/internal``). It compares in constant time and rejects empty/missing secrets so
a blank env var can never open the gate.
"""

import hmac

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from pycil.config import settings

INTERNAL_PREFIX = "/internal"


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl is not None and cl.isdigit() and int(cl) > self.max_bytes:
            return JSONResponse(
                status_code=413,
                content={"error": {"code": "payload_too_large", "message": "Body too large"}},
            )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


class InternalSecretMiddleware(BaseHTTPMiddleware):
    """Constant-time guard on /internal/* routes; empty/missing secret rejected."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(INTERNAL_PREFIX):
            presented = request.headers.get("X-Internal-Secret", "")
            expected = settings.internal_secret
            if not presented or not expected or not hmac.compare_digest(presented, expected):
                return JSONResponse(
                    status_code=401,
                    content={"error": {"code": "unauthorized", "message": "Bad internal secret"}},
                )
        return await call_next(request)


def install_middleware(app: FastAPI) -> None:
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
