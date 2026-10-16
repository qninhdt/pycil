"""Safe errors, correlation, CORS and bounded bodies without buffering responses."""

import time
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid7

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import iter_route_contexts
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from pydantic import BaseModel, ConfigDict
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pycil.infrastructure.observability import bind_contextvars, clear_contextvars, get_logger
from pycil.utils.http import http_status_phrase, normalize_http_method

logger = get_logger("pycil.app.http")


class HttpTelemetry:
    def __init__(self, app: ASGIApp):
        self.app = app

        def span_details(scope: dict[str, object]) -> tuple[str, dict[str, str]]:
            return (
                f"{scope['method']} {scope['path']}",
                {"http.route": str(scope["path"])},
            )

        self.instrumented = OpenTelemetryMiddleware(
            self.dispatch,
            default_span_details=span_details,
            # A nonempty never-match pattern also overrides capture-header env settings.
            http_capture_headers_server_request=["(?!)"],
            http_capture_headers_server_response=["(?!)"],
            exclude_spans=["receive", "send"],
        )

    async def dispatch(self, scope: Scope, receive: Receive, send: Send):
        await self.app(scope["pycil.original_scope"], receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        route = "unmatched"
        for candidate in iter_route_contexts(scope["app"].routes):
            match, _ = candidate.matches(scope)
            if match != Match.NONE:
                route = candidate.path or "unmatched"
                if match == Match.FULL:
                    break
        method = normalize_http_method(scope["method"])
        scope.setdefault("state", {})["telemetry_route"] = route
        scope["state"]["telemetry_method"] = method
        # Instrument a sanitized scope; routing/auth/body handling retain the original.
        safe = dict(
            scope,
            path=route,
            raw_path=route.encode(),
            root_path="",
            query_string=b"",
            method=method,
            scheme="https" if scope.get("scheme") == "https" else "http",
            server=("pycil-api", 0),
            client=None,
            headers=[
                (k, v)
                for k, v in scope.get("headers", [])
                if k.lower() in {b"traceparent", b"tracestate"}
            ],
            route=SimpleNamespace(path_format=route),
        )
        safe["pycil.original_scope"] = scope
        await self.instrumented(safe, receive, send)


class ProblemResponse(JSONResponse):
    media_type = "application/problem+json"


_http_status_phrase = http_status_phrase


class Problem(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        *,
        detail: str | None = None,
        title: str | None = None,
    ):
        self.status = status
        self.code = code
        self.detail = detail
        self.title = title or _http_status_phrase(status)
        super().__init__(code)


class InvalidParam(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    reason: str


class ProblemDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    code: str
    request_id: str | None = None
    invalid_params: list[InvalidParam] | None = None
    error: str


ErrorResponse = ProblemDetails


async def problem_response(request: Request, error: Problem) -> ProblemResponse:
    headers = {"WWW-Authenticate": "Bearer"} if error.status == 401 else None
    request_id = getattr(request.state, "request_id", None)
    payload: dict[str, object] = {
        "type": "about:blank",
        "title": error.title,
        "status": error.status,
        "detail": error.detail,
        "instance": request.url.path,
        "code": error.code,
        "request_id": request_id,
        "invalid_params": None,
        "error": error.code,
    }
    return ProblemResponse(payload, status_code=error.status, headers=headers)


async def validation_response(request: Request, error: RequestValidationError) -> ProblemResponse:
    # FastAPI's default includes input values, which can contain credentials/content.
    logger.warning(
        "http_validation_failed", fields=[list(e.get("loc", [])) for e in error.errors()]
    )
    request_id = getattr(request.state, "request_id", None)
    invalid_params = [
        InvalidParam(
            name=".".join(str(loc) for loc in e.get("loc", []) if loc != "body") or "body",
            reason=str(e.get("msg", "Invalid value")),
        ).model_dump()
        for e in error.errors()
    ]
    payload: dict[str, object] = {
        "type": "about:blank",
        "title": "Unprocessable Content",
        "status": 422,
        "detail": "Request validation failed.",
        "instance": request.url.path,
        "code": "invalid_request",
        "request_id": request_id,
        "invalid_params": invalid_params,
        "error": "invalid_request",
    }
    return ProblemResponse(payload, status_code=422)


async def http_error_response(request: Request, error: HTTPException) -> ProblemResponse:
    codes = {404: "not_found", 405: "method_not_allowed", 401: "authentication_required"}
    code = codes.get(error.status_code, "request_failed")
    title = _http_status_phrase(error.status_code)
    request_id = getattr(request.state, "request_id", None)
    detail = error.detail if error.detail and error.detail != title else None
    payload: dict[str, object] = {
        "type": "about:blank",
        "title": title,
        "status": error.status_code,
        "detail": detail,
        "instance": request.url.path,
        "code": code,
        "request_id": request_id,
        "invalid_params": None,
        "error": code,
    }
    return ProblemResponse(payload, status_code=error.status_code, headers=error.headers)


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
            method=scope.get("state", {}).get("telemetry_method", scope.get("method")),
            route=scope.get("state", {}).get("telemetry_route", "unmatched"),
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
                payload = {
                    "type": "about:blank",
                    "title": "Internal Server Error",
                    "status": 500,
                    "detail": "An internal error occurred.",
                    "instance": scope.get("path", ""),
                    "code": "internal_error",
                    "request_id": request_id,
                    "invalid_params": None,
                    "error": "internal_error",
                }
                await ProblemResponse(payload, status_code=500)(scope, receive, correlated_send)
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
                expose_headers=["X-Request-ID", "Location", "Retry-After"],
            )
        await self.cors(scope, receive, send)
