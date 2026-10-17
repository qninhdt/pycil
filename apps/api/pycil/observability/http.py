"""Sanitized native HTTP client and ASGI instrumentation."""

from types import SimpleNamespace
from typing import Any

import httpx
from fastapi.routing import iter_route_contexts
from opentelemetry import trace
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from starlette.routing import Match
from starlette.types import ASGIApp, Receive, Scope, Send

from pycil.utils.http import normalize_http_method

_http_tracer = trace.get_tracer("pycil.http.client")


class ObservedAsyncClient(httpx.AsyncClient):
    """Measure public send calls without collecting URLs, headers or content."""

    async def send(
        self, request: httpx.Request, *, stream: bool = False, **kwargs: Any
    ) -> httpx.Response:
        method = normalize_http_method(request.method)
        # Hooks run after native instrumentation has already collected request data.
        with _http_tracer.start_as_current_span(
            method,
            kind=trace.SpanKind.CLIENT,
            attributes={"http.request.method": method, "pycil.http.stream": stream},
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                response = await super().send(request, stream=stream, **kwargs)
            except BaseException as exc:
                span.set_attribute("error.type", type(exc).__name__)
                span.set_status(trace.StatusCode.ERROR)
                raise
            span.set_attribute("http.response.status_code", response.status_code)
            if response.status_code >= 400:
                span.set_attribute("error.type", str(response.status_code))
                span.set_status(trace.StatusCode.ERROR)
            return response


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
