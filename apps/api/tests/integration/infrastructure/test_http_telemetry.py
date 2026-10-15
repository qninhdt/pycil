import json
import logging
from functools import partial
from types import SimpleNamespace

import pytest
import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from pycil.app import http
from pycil.app.config import load_config
from pycil.app.factory import create_app
from pycil.infrastructure import observability


@pytest.mark.parametrize("sample_ratio", [0, 1])
async def test_http_templates_privacy_metrics_and_log_correlation(
    monkeypatch, capsys, sample_ratio
):
    reader = InMemoryMetricReader()
    meter = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    exporter = InMemorySpanExporter()
    tracer = TracerProvider(
        sampler=ParentBased(TraceIdRatioBased(sample_ratio)), shutdown_on_exit=False
    )
    tracer.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(
        http,
        "OpenTelemetryMiddleware",
        partial(http.OpenTelemetryMiddleware, tracer_provider=tracer, meter_provider=meter),
    )
    monkeypatch.setenv("OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST", ".*")
    monkeypatch.setenv("OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE", ".*")
    monkeypatch.setattr(
        observability,
        "_log_resource",
        {
            "service.name": "pycil-api",
            "service.version": "test-release",
            "deployment.environment": "local",
        },
    )
    logging_state = logging.getLogger().handlers[:], logging.getLogger().level
    structlog_state = structlog.get_config()
    try:
        app = create_app()
        app.state.config = load_config()
        app.state.deployment = SimpleNamespace(allowed_origins=[])
        router = APIRouter(prefix="/controlled")

        @router.post("/words/{word_id}")
        async def word(word_id: int, request: Request):
            assert request.query_params["query"] == "private-query"
            assert await request.body() == b"private-body"
            assert request.headers["authorization"] == "Bearer private-token"
            observability.get_logger(__name__).info("controlled_read")
            logging.getLogger("controlled.stdlib").info("controlled_stdlib")
            return JSONResponse({"id": word_id}, headers={"X-Private": "private-response"})

        @router.get("/failure")
        async def failure():
            raise RuntimeError("private-exception-payload")

        app.include_router(router)
        async with AsyncClient(transport=ASGITransport(app), base_url="https://api.test") as client:
            for identifier in (123456, 654321):
                parent_flags = "01" if sample_ratio else "00"
                response = await client.post(
                    f"/controlled/words/{identifier}?query=private-query",
                    content=b"private-body",
                    headers={
                        "Authorization": "Bearer private-token",
                        "Cookie": "private-cookie",
                        "User-Agent": "private-agent",
                        "Host": "private-host.test",
                        "traceparent": f"00-{'a' * 32}-{'b' * 16}-{parent_flags}",
                    },
                )
                assert response.json() == {"id": identifier}
                assert response.headers["x-request-id"]
            for path in ("/private-missing-one", "/private-missing-two"):
                assert (await client.get(path)).status_code == 404
            assert (await client.get("/controlled/failure")).status_code == 500
        observability.get_logger(__name__).info("outside_request")
        events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
        spans = exporter.get_finished_spans()
        assert len(spans) == (5 if sample_ratio else 0)
        if spans:
            assert all(span.kind == trace.SpanKind.SERVER for span in spans)
            assert {span.name for span in spans} == {
                "POST /controlled/words/{word_id}",
                "GET unmatched",
                "GET /controlled/failure",
            }
            assert next(s for s in spans if s.name.endswith("failure")).status.status_code == (
                trace.StatusCode.ERROR
            )
            reads = [s for s in spans if s.name.startswith("POST")]
            assert all(s.context.trace_id == int("a" * 32, 16) for s in reads)
            assert all(s.parent.span_id == int("b" * 16, 16) for s in reads)
            assert all(not s.events for s in spans)
        logs = [event for event in events if event["event"] == "http_request_completed"]
        assert len(logs) == 5
        for event in logs:
            assert len(event["trace_id"]) == 32
            assert len(event["span_id"]) == 16
            assert event["service.version"] == "test-release"
            assert "path" not in event
            if spans:
                assert any(f"{s.context.span_id:016x}" == event["span_id"] for s in spans)
        stdlib_logs = [e for e in events if e["event"] == "controlled_stdlib"]
        assert len(stdlib_logs) == 2
        assert all(
            len(e["trace_id"]) == 32 and e["service.version"] == "test-release" for e in stdlib_logs
        )
        outside = next(event for event in events if event["event"] == "outside_request")
        assert "trace_id" not in outside and "request_id" not in outside
        assert outside["service.name"] == "pycil-api"
        data = reader.get_metrics_data()
        measurements = [
            m for r in data.resource_metrics for s in r.scope_metrics for m in s.metrics
        ]
        duration = next(m for m in measurements if m.name == "http.server.duration")
        assert sum(p.count for p in duration.data.data_points) == 5
        assert {p.attributes["http.target"] for p in duration.data.data_points} == {
            "/controlled/words/{word_id}",
            "unmatched",
            "/controlled/failure",
        }
        active = next(m for m in measurements if m.name == "http.server.active_requests")
        assert all(p.value == 0 for p in active.data.data_points)
        payload = str([span.to_json() for span in spans]) + str(data) + str(events)
        for forbidden in ("private-", "/words/123456", "/words/654321"):
            assert forbidden not in payload
    finally:
        tracer.shutdown()
        meter.shutdown()
        logging.getLogger().handlers, logging.getLogger().level = logging_state
        structlog.configure(**structlog_state)
