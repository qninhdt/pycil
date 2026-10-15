"""Safe errors, correlation, CORS and bounded bodies without buffering responses."""

import time
from typing import Any, cast
from uuid import UUID, uuid7

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pycil.infrastructure.observability import bind_contextvars, clear_contextvars, get_logger

logger = get_logger("pycil.app.http")


class Problem(Exception):
    def __init__(self, status: int, code: str):
        self.status = status
        self.code = code
        super().__init__(code)


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: str


async def problem_response(request: Request, error: Problem):
    headers = {"WWW-Authenticate": "Bearer"} if error.status == 401 else None
    return JSONResponse({"error": error.code}, status_code=error.status, headers=headers)


async def validation_response(request: Request, error: RequestValidationError):
    # FastAPI's default includes input values, which can contain credentials/content.
    logger.warning(
        "http_validation_failed", fields=[list(e.get("loc", [])) for e in error.errors()]
    )
    return JSONResponse({"error": "invalid_request"}, status_code=422)


async def http_error_response(request: Request, error: HTTPException):
    codes = {404: "not_found", 405: "method_not_allowed", 401: "authentication_required"}
    return JSONResponse(
        {"error": codes.get(error.status_code, "request_failed")},
        status_code=error.status_code,
        headers=error.headers,
    )


class RequestBoundary:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        clear_contextvars()
        incoming = Headers(scope=scope).get("x-request-id", "")
        try:
            request_id = str(UUID(incoming))
        except ValueError:
            request_id = str(uuid7())
        scope.setdefault("state", {})["request_id"] = request_id
        bind_contextvars(
            request_id=request_id,
            method=scope.get("method"),
            path=scope.get("path"),
        )
        started_at = time.perf_counter()
        started = False
        status_code: int | None = None

        async def correlated_send(message: Message) -> None:
            nonlocal started, status_code
            if message["type"] == "http.response.start":
                status_code = cast(int | None, message.get("status"))
                MutableHeaders(scope=cast(Any, message))["X-Request-ID"] = request_id
                started = True
            await send(message)

        try:
            try:
                await self.app(scope, receive, correlated_send)
            except Exception:
                # Log correlation only: raw provider/DB exceptions can contain secrets.
                logger.error("request_failed")
                if started:
                    # Never send a second status or turn a truncated stream into success.
                    raise RuntimeError(f"Response interrupted; request_id={request_id}") from None
                await JSONResponse({"error": "internal_error"}, status_code=500)(
                    scope, receive, correlated_send
                )
            if status_code is not None:
                logger.info(
                    "http_request_completed",
                    status_code=status_code,
                    duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
                )
        finally:
            clear_contextvars()


class RuntimeCORS:
    def __init__(self, app: ASGIApp):
        self.app = app
        self.cors = None
        self.origins = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        deployment = getattr(scope["app"].state, "deployment", None)
        base_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
        if deployment and deployment.allowed_origins:
            origins = tuple(dict.fromkeys(base_origins + list(deployment.allowed_origins)))
        else:
            origins = tuple(base_origins)
        if self.cors is None or self.origins != origins:
            self.origins = origins
            self.cors = CORSMiddleware(
                self.app,
                allow_origins=origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
                expose_headers=["*"],
            )
        await self.cors(scope, receive, send)


class BodyLimit:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        max_bytes = scope["app"].state.config.runtime.http.max_body_bytes
        declared = Headers(scope=scope).get("content-length")
        if declared is not None:
            try:
                length = int(declared)
                if length < 0:
                    raise ValueError
            except ValueError:
                logger.warning("http_invalid_content_length", content_length_raw=declared)
                return await JSONResponse({"error": "invalid_request"}, status_code=400)(
                    scope, receive, send
                )
            if length > max_bytes:
                logger.warning(
                    "http_body_limit_exceeded",
                    max_bytes=max_bytes,
                    content_length=length,
                    phase="header",
                )
                return await JSONResponse({"error": "body_too_large"}, status_code=413)(
                    scope, receive, send
                )
        # Bound the request before routing/streaming: chunked bodies cannot bypass it.
        body = bytearray()
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > max_bytes:
                logger.warning(
                    "http_body_limit_exceeded",
                    max_bytes=max_bytes,
                    content_length=size,
                    phase="stream",
                )
                return await JSONResponse({"error": "body_too_large"}, status_code=413)(
                    scope, receive, send
                )
            body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)
