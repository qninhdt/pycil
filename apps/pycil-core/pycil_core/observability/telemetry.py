"""OpenTelemetry boot (P6 phase 5).

Single-call initializer: read OTEL_* env, install OTLP exporter for traces
and metrics, instrument FastAPI / SQLAlchemy / Redis / httpx automatically.

No-op when OTEL_EXPORTER_OTLP_ENDPOINT is missing — keeps dev runs free
of trace overhead and external dependency.
"""
from __future__ import annotations

import logging
import os
from typing import Any

_log = logging.getLogger(__name__)


def setup_telemetry(*, app: Any | None = None, service_name: str = "pycil-core") -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        _log.info("otel_disabled", extra={"reason": "OTEL_EXPORTER_OTLP_ENDPOINT not set"})
        return
    try:
        from opentelemetry import trace  # type: ignore[reportMissingImports]
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource  # type: ignore
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore
    except ImportError:
        _log.warning("otel_skipped_sdk_missing")
        return

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "pycil",
            "deployment.environment": os.getenv("APP_ENV", "dev"),
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    _try_instrument("opentelemetry.instrumentation.fastapi", "FastAPIInstrumentor", app)
    _try_instrument("opentelemetry.instrumentation.sqlalchemy", "SQLAlchemyInstrumentor")
    _try_instrument("opentelemetry.instrumentation.redis", "RedisInstrumentor")
    _try_instrument("opentelemetry.instrumentation.httpx", "HTTPXClientInstrumentor")
    _log.info("otel_enabled", extra={"endpoint": endpoint, "service": service_name})


def _try_instrument(module: str, klass: str, app: Any | None = None) -> None:
    try:
        mod = __import__(module, fromlist=[klass])
        instrumentor = getattr(mod, klass)()
        if app is not None and klass == "FastAPIInstrumentor":
            instrumentor.instrument_app(app)
        else:
            instrumentor.instrument()
    except Exception as exc:  # noqa: BLE001
        _log.debug(
            "otel_instrumentation_skipped",
            extra={"module": module, "err": str(exc)[:120]},
        )
