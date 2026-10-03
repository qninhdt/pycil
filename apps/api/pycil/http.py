"""Safe errors, correlation, CORS and bounded bodies without buffering responses."""

import logging
from uuid import UUID, uuid7

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send


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
        incoming = Headers(scope=scope).get("x-request-id", "")
        try:
            request_id = str(UUID(incoming))
        except ValueError:
            request_id = str(uuid7())
        scope.setdefault("state", {})["request_id"] = request_id
        started = False

        async def correlated_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
                started = True
            await send(message)

        try:
            await self.app(scope, receive, correlated_send)
        except Exception:
            # Log correlation only: raw provider/DB exceptions can contain secrets.
            logging.getLogger("pycil.http").error("request_failed request_id=%s", request_id)
            if started:
                # Never send a second status or turn a truncated stream into success.
                raise RuntimeError(f"Response interrupted; request_id={request_id}") from None
            await JSONResponse({"error": "internal_error"}, status_code=500)(
                scope, receive, correlated_send
            )


class RuntimeCORS:
    def __init__(self, app: ASGIApp):
        self.app = app
        self.cors = None
        self.origins = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        deployment = getattr(scope["app"].state, "deployment", None)
        origins = tuple(deployment.allowed_origins) if deployment else ()
        if self.cors is None or self.origins != origins:
            self.origins = origins
            self.cors = CORSMiddleware(
                self.app,
                allow_origins=origins,
                allow_credentials=True,
                allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
                expose_headers=["X-Request-ID"],
            )
        await self.cors(scope, receive, send)


class BodyLimit:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        max_bytes = scope["app"].state.product.http.max_body_bytes
        declared = Headers(scope=scope).get("content-length")
        if declared is not None:
            try:
                length = int(declared)
                if length < 0:
                    raise ValueError
            except ValueError:
                return await JSONResponse({"error": "invalid_request"}, status_code=400)(
                    scope, receive, send
                )
            if length > max_bytes:
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
