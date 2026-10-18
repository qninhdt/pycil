import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from time import perf_counter

import pytest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest


def deployment_values(**overrides):
    return (
        dict(
            db_url="postgresql+asyncpg://test:test@db.test/app",
            redis_url="redis://redis.test/0",
            clerk_jwks_url="https://identity.test/jwks",
            clerk_issuer="https://identity.test",
            clerk_audience=None,
            clerk_secret_key="test-only",
            allowed_origins=[],
            llm_api_key="test-only",
            llm_base_url="https://provider.test/v1",
            decision_api_key="test-only",
            decision_base_url="https://decision.test",
        )
        | overrides
    )


@pytest.mark.parametrize(
    "response_status, startup_failure, tuned",
    [(200, False, False), (503, False, False), (200, True, False), (200, False, True)],
)
def test_real_otlp_transport_and_resource_cleanup(response_status, startup_failure, tuned):
    requests = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(
                (self.path, self.rfile.read(int(self.headers["Content-Length"])), perf_counter())
            )
            self.send_response(response_status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Receiver)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        result = subprocess.run(
            [sys.executable, "-c", CHILD, str(int(startup_failure)), str(int(tuned))],
            input=json.dumps(
                deployment_values(
                    db_url="postgresql+asyncpg://test:test@127.0.0.1:1/app",
                    otel_endpoint=f"http://127.0.0.1:{server.server_port}/otlp",
                    service_version="test-release-immutable",
                    git_sha="a" * 40,
                    deployment_environment="local",
                    otel_sample_ratio=1,
                )
            ),
            text=True,
            capture_output=True,
            timeout=12,
        )
    finally:
        server.shutdown()
        worker.join(timeout=2)
        server.server_close()
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout.splitlines()[-1])
    closing_at = output.pop("closing_at")
    assert output == {
        "business_result": None if startup_failure else 42,
        "workers_closed": True,
    }
    traces = [
        ExportTraceServiceRequest.FromString(body)
        for path, body, _at in requests
        if path == "/otlp/v1/traces"
    ]
    metrics = [
        ExportMetricsServiceRequest.FromString(body)
        for path, body, _at in requests
        if path == "/otlp/v1/metrics"
    ]
    assert metrics
    if tuned:
        assert {path for path, _body, at in requests if at < closing_at} >= {
            "/otlp/v1/traces",
            "/otlp/v1/metrics",
        }
    if startup_failure:
        assert not traces
        return
    assert traces
    spans = [
        span
        for request in traces
        for batch in request.resource_spans
        for scope in batch.scope_spans
        for span in scope.spans
    ]
    assert {span.name for span in spans} == {"controlled-work", "GET /livez"}
    http_span = next(span for span in spans if span.name == "GET /livez")
    logs = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    completion = next(event for event in logs if event.get("event") == "http_request_completed")
    assert completion["trace_id"] == http_span.trace_id.hex()
    assert completion["span_id"] == http_span.span_id.hex()
    assert completion["service.version"] == "test-release-immutable"
    resource = {
        item.key: item.value.string_value
        for item in traces[0].resource_spans[0].resource.attributes
    }
    assert resource["service.name"] == "pycil-api"
    assert resource["service.version"] == "test-release-immutable"
    assert resource["deployment.environment.name"] == "local"
    assert resource["vcs.ref.head.revision"] == "a" * 40
    assert resource["service.instance.id"]
    observations = [
        metric
        for request in metrics
        for batch in request.resource_metrics
        for scope in batch.scope_metrics
        for metric in scope.metrics
    ]
    assert {metric.name for metric in observations} >= {
        "pycil.db.pool.acquire.duration",
        "pycil.store.requests",
        "pycil.store.evictions",
        "pycil.store.entries",
        "pycil.store.capacity",
    }
    assert "test-only" not in str(traces) + str(metrics)
    assert "private-cache-key" not in str(traces) + str(metrics)


# A fresh process exercises the public OTel globals without resetting SDK internals.
CHILD = """
import asyncio
import json
import sys
import threading
from time import perf_counter
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from pycil.app.config import load_config
from pycil.app.factory import create_app
from pycil.app.resources import api_resources
from pycil.app.settings import ApiSettings
from pycil.infrastructure.kv_store import InMemoryStore
from pycil.observability.stores import ObservedInMemoryStore
from pycil.observability import record_database_duration, telemetry

async def main():
    deployment = ApiSettings(**json.load(sys.stdin))
    config = load_config()
    if sys.argv[2] == "1":
        data = config.model_dump()
        data["system"]["telemetry"]["traces"].update(
            max_queue_size=8, max_export_batch_size=4, schedule_delay_seconds=0.05,
            export_timeout_seconds=0.5,
        )
        data["system"]["telemetry"]["metrics"].update(
            export_interval_seconds=0.05, export_timeout_seconds=0.5,
            shutdown_timeout_seconds=1,
        )
        config = type(config).model_validate(data)
    tracer = trace.get_tracer("test-before-sdk")
    started = perf_counter()
    business_result = None
    closing_at = None
    if sys.argv[1] == "1":
        try:
            async with api_resources(config, deployment):
                raise AssertionError("unreachable database unexpectedly initialized")
        except RuntimeError as error:
            assert "Runtime initialization failed" in str(error)
    else:
        async with telemetry(deployment, config.system.telemetry):
            provider = trace.get_tracer_provider()
            with tracer.start_as_current_span("controlled-work"):
                record_database_duration("pool.acquire", "application", perf_counter())
                store = ObservedInMemoryStore(1, 60, name="word")
                store.put("private-cache-key-A", "A")
                assert store.get("private-cache-key-A") == "A"
                store.put("private-cache-key-B", "B")
                assert store.get("private-cache-key-A") is None
                business_result = 6 * 7
            assert trace.get_tracer_provider() is provider
            assert perf_counter() - started < 1, "export blocked business work"
            app = create_app()
            app.state.config = load_config()
            app.state.deployment = deployment
            async with AsyncClient(
                transport=ASGITransport(app), base_url="http://api.test"
            ) as http:
                response = await http.get("/livez")
                assert response.status_code == 200
                assert response.headers["x-request-id"]
            if sys.argv[2] == "1":
                await asyncio.sleep(0.5)
            closing_at = perf_counter()
    assert not any(t.name.startswith("Otel") for t in threading.enumerate())
    try:
        async with telemetry(deployment, config.system.telemetry):
            raise AssertionError("second provider initialization was allowed")
    except RuntimeError as error:
        assert "already initialized" in str(error)
    print(json.dumps({
        "business_result": business_result, "workers_closed": True, "closing_at": closing_at,
    }))

asyncio.run(main())
"""
