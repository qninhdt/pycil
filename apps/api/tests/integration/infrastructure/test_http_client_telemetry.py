import asyncio
import logging
from functools import partial
from types import SimpleNamespace

import httpx
import pytest
import structlog
from opentelemetry import trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from pycil.app import http
from pycil.app.config import load_config
from pycil.app.factory import create_app
from pycil.infrastructure import observability
from pycil.infrastructure.observability import ObservedAsyncClient


@pytest.fixture
def client_telemetry(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    meter = MeterProvider(metric_readers=[InMemoryMetricReader()], shutdown_on_exit=False)
    tracer = provider.get_tracer("pycil.http.client")
    monkeypatch.setattr(observability, "_http_tracer", tracer)
    monkeypatch.setattr(
        http,
        "OpenTelemetryMiddleware",
        partial(http.OpenTelemetryMiddleware, tracer_provider=provider, meter_provider=meter),
    )
    monkeypatch.setenv("OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST", ".*")
    monkeypatch.setenv("OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_RESPONSE", ".*")
    logging_state = logging.getLogger().handlers[:], logging.getLogger().level
    structlog_state = structlog.get_config()
    try:
        yield SimpleNamespace(exporter=exporter, tracer=tracer)
    finally:
        logging.getLogger().handlers, logging.getLogger().level = logging_state
        structlog.configure(**structlog_state)
        provider.shutdown()
        meter.shutdown()


async def test_http_calls_have_safe_child_spans_and_preserve_requests(client_telemetry, capsys):
    signals = client_telemetry
    received = []
    hooks = []

    async def provider(request):
        received.append(request)
        return httpx.Response(
            503 if len(received) == 1 else 200,
            content=b"private-response",
            headers={"X-Private": "private-header"},
        )

    async def on_response(response):
        hooks.append(response.status_code)
        await response.aread()

    app = create_app()
    app.state.config = load_config()
    app.state.deployment = SimpleNamespace(allowed_origins=[])
    async with ObservedAsyncClient(
        transport=httpx.MockTransport(provider), event_hooks={"response": [on_response]}
    ) as outbound:

        @app.post("/controlled/outbound")
        async def call_provider():
            for method in ("POST", "POST", "private-method"):
                response = await outbound.request(
                    method,
                    "https://private-host.test/private-path?key=private-query",
                    content=b"private-body",
                    headers={"Authorization": "Bearer private-secret"},
                )
                assert response.content == b"private-response"
            return {"status": "ok"}

        capsys.readouterr()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="https://api.test"
        ) as incoming:
            assert (await incoming.post("/controlled/outbound")).json() == {"status": "ok"}
    assert outbound.is_closed
    assert hooks == [503, 200, 200]
    assert len(received) == 3
    for request in received:
        assert request.headers["authorization"] == "Bearer private-secret"
        assert request.content == b"private-body"
        assert request.url.query == b"key=private-query"
        assert "traceparent" not in request.headers and "baggage" not in request.headers
    spans = signals.exporter.get_finished_spans()
    (server,) = [s for s in spans if s.kind == trace.SpanKind.SERVER]
    calls = [s for s in spans if s.kind == trace.SpanKind.CLIENT]
    assert len(calls) == 3 and [s.name for s in calls] == ["POST", "POST", "_OTHER"]
    assert calls[0].status.status_code == trace.StatusCode.ERROR
    assert calls[0].attributes["error.type"] == "503"
    assert all(s.status.status_code == trace.StatusCode.UNSET for s in calls[1:])
    for span in calls:
        assert span.parent.span_id == server.context.span_id
        assert span.context.trace_id == server.context.trace_id
        assert server.start_time <= span.start_time <= span.end_time <= server.end_time
        assert set(span.attributes) <= {
            "http.request.method",
            "http.response.status_code",
            "pycil.http.stream",
            "error.type",
        }
        assert not span.attributes["pycil.http.stream"]
        assert not span.events and not span.status.description
    assert "private-" not in str([s.to_json() for s in spans]) + capsys.readouterr().out


@pytest.mark.parametrize(
    "error_type", [httpx.ConnectError, httpx.ReadTimeout, asyncio.CancelledError]
)
async def test_http_failures_and_cancellation_close_spans_without_content(
    client_telemetry, error_type
):
    failure = error_type("private-exception-with-URL-and-secret")

    async def provider(request):
        raise failure

    with client_telemetry.tracer.start_as_current_span("controlled-parent"):
        async with ObservedAsyncClient(transport=httpx.MockTransport(provider)) as client:
            with pytest.raises(error_type) as caught:
                await client.get("https://private-host.test/private-path")
            assert caught.value is failure
    (span,) = [s for s in client_telemetry.exporter.get_finished_spans() if s.name == "GET"]
    assert span.end_time and span.status.status_code == trace.StatusCode.ERROR
    assert span.attributes["error.type"] == error_type.__name__
    assert not span.events and not span.status.description
    assert "private-" not in span.to_json()
    assert client.is_closed


async def test_streaming_returns_headers_without_reading_body(client_telemetry):
    class Body(httpx.AsyncByteStream):
        read = closed = False

        async def __aiter__(self):
            self.read = True
            yield b"private-first-chunk"
            raise httpx.ReadError("private-late-body-error")

        async def aclose(self):
            self.closed = True

    body = Body()

    async def provider(request):
        return httpx.Response(200, stream=body)

    with client_telemetry.tracer.start_as_current_span("controlled-parent"):
        async with ObservedAsyncClient(transport=httpx.MockTransport(provider)) as client:
            async with client.stream(
                "POST", "https://private-host.test", content=b"private-prompt"
            ) as response:
                assert not body.read
                (span,) = client_telemetry.exporter.get_finished_spans()
                assert span.name == "POST" and span.end_time
                assert span.attributes["pycil.http.stream"]
                assert span.attributes["http.response.status_code"] == 200
                with pytest.raises(httpx.ReadError):
                    async for chunk in response.aiter_bytes():
                        assert chunk == b"private-first-chunk"
    assert body.read and body.closed and client.is_closed
    assert span.status.status_code == trace.StatusCode.UNSET
    assert not span.events and "private-" not in span.to_json()
