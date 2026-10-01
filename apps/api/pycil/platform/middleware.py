"""HTTP middleware: body-size cap, CORS, security headers, internal-secret guard.

The internal-secret guard protects worker→api callback routes (prefix
``/internal``). It compares in constant time and rejects empty/missing secrets so
a blank env var can never open the gate.
"""

import hmac
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid7

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from pycil.platform.errors import error_envelope
from pycil.platform.settings import settings
from pycil.platform.telemetry import metrics

INTERNAL_PREFIX = "/internal"


def _request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if request_id is None:
        request_id = request.headers.get("X-Request-ID") or uuid7().hex
        request.state.request_id = request_id
    return request_id


def _middleware_error(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    request_id = _request_id(request)
    response = JSONResponse(
        status_code=status_code,
        content=error_envelope(request, status=status_code, code=code, message=message).model_dump(
            by_alias=True, exclude_none=True
        ),
        media_type="application/problem+json",
    )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _asgi_error_headers(request_id: str) -> list[tuple[bytes, bytes]]:
    return [
        (b"content-type", b"application/problem+json"),
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
        request_id = headers.get(b"x-request-id", b"").decode() or uuid7().hex
        if (
            content_length is not None
            and content_length.isdigit()
            and int(content_length) > self.max_bytes
        ):
            await self._send_too_large(scope, send, request_id)
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
                await self._send_too_large(scope, send, request_id)
                return
            messages.append(message)
            if not message.get("more_body", False):
                break

        async def replay_receive() -> dict:
            if messages:
                return messages.pop(0)
            # Keep the original receive channel alive after replaying the buffered
            # body. Streaming responses use it to distinguish a real client
            # disconnect from the end of the request body; returning disconnect
            # here cancels every SSE generator immediately after its 200 headers.
            return await receive()

        await self.app(scope, replay_receive, send)

    async def _send_too_large(self, scope: dict[str, Any], send, request_id: str) -> None:
        # Built from the same helper every other rejection uses, rather than a
        # hand-written dict: this path runs before FastAPI has a Request, but the
        # document it produces is the public error contract and a second copy of it
        # is how the two drift. `error_envelope` reads only `path` and the request
        # id off the request, both of which are already in the scope.
        request = Request(scope)
        request.state.request_id = request_id
        payload = (
            error_envelope(
                request,
                status=413,
                code="payload_too_large",
                message="Body too large",
            )
            .model_dump_json(by_alias=True, exclude_none=True)
            .encode()
        )
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": _asgi_error_headers(request_id)
                + [(b"content-length", str(len(payload)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": payload})


def _state(scope: dict[str, Any]) -> dict[str, Any]:
    return scope.setdefault("state", {})


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                    ]
                )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestIdMiddleware:
    """Attach an opaque correlation id to every response and error envelope."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        request_id = headers.get(b"x-request-id", b"").decode() or uuid7().hex
        _state(scope)["request_id"] = request_id

        async def send_with_request_id(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
                metrics.increment("pycil_http_requests_total")
                metrics.increment(f"pycil_http_status_{message['status']}_total")
            await send(message)

        await self.app(scope, receive, send_with_request_id)


class InternalSecretMiddleware:
    """Constant-time guard on /internal/* routes; empty/missing secret rejected."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        if path.startswith(INTERNAL_PREFIX):
            presented = headers.get(b"x-internal-secret", b"").decode()
            expected = settings.internal_secret
            if not presented or not expected or not hmac.compare_digest(presented, expected):
                request = Request(scope, receive=receive)
                response = _middleware_error(request, 401, "unauthorized", "Bad internal secret")
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def install_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(InternalSecretMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_body_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
