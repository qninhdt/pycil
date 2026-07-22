"""HTTP middleware: body-size cap, CORS, security headers, internal-secret guard.

The internal-secret guard protects worker→api callback routes (prefix
``/internal``). It compares in constant time and rejects empty/missing secrets so
a blank env var can never open the gate.
"""

import hmac
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from pycil.common.errors import ErrorDetail, ErrorEnvelope
from pycil.config import settings
from pycil.observability import metrics

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


def _asgi_error_headers(request_id: str) -> list[tuple[bytes, bytes]]:
    return [
        (b"content-type", b"application/json"),
        (b"x-request-id", request_id.encode()),
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"no-referrer"),
    ]


class BodySizeLimitMiddleware:
    """Reject bodies over the cap, including chunked requests without a length.

    The request is buffered only up to the configured maximum before the downstream
    ASGI app is called. This prevents a chunked client from bypassing the cap by
    omitting ``Content-Length``.
    """

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict[str, Any], receive: Callable[[], Awaitable[dict]], send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        request_id = headers.get(b"x-request-id", b"").decode() or uuid4().hex
        if (
            content_length is not None
            and content_length.isdigit()
            and int(content_length) > self.max_bytes
        ):
            await self._send_too_large(send, request_id)
            return

        messages: list[dict] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                messages.append(message)
                break
            size += len(message.get("body", b""))
            if size > self.max_bytes:
                await self._send_too_large(send, request_id)
                return
            messages.append(message)
            if not message.get("more_body", False):
                break

        async def replay_receive() -> dict:
            if messages:
                return messages.pop(0)
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)

    async def _send_too_large(self, send, request_id: str) -> None:
        import json

        payload = json.dumps(
            ErrorEnvelope(
                error=ErrorDetail(
                    code="payload_too_large",
                    message="Body too large",
                    request_id=request_id,
                )
            ).model_dump(by_alias=True),
            separators=(",", ":"),
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": _asgi_error_headers(request_id)
                + [(b"content-length", str(len(payload)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": payload})


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
        metrics.increment("pycil_http_requests_total")
        metrics.increment(f"pycil_http_status_{response.status_code}_total")
        return response


class InternalSecretMiddleware(BaseHTTPMiddleware):
    """Constant-time guard on /internal/* routes; empty/missing secret rejected."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(INTERNAL_PREFIX):
            if request.url.path == "/internal/realtime/subscribe":
                presented = request.headers.get("X-Centrifugo-Subscribe-Proxy-Secret", "")
                expected = settings.centrifugo_subscribe_proxy_secret
            else:
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
