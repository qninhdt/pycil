"""Structured logging, application measurements and process-owned OTel SDK export."""

import asyncio
import logging
import os
import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import ExitStack, asynccontextmanager, contextmanager
from enum import StrEnum
from time import perf_counter
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

import httpx
import orjson
import structlog
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from pycil.app.settings import ProcessSettings

if TYPE_CHECKING:
    from pycil.app.config import TelemetryRuntime

_telemetry_started = False
_log_resource: dict[str, str] = {}
_http_tracer = trace.get_tracer("pycil.http.client")


class ObservedAsyncClient(httpx.AsyncClient):
    """Measure public send calls without collecting URLs, headers or content."""

    async def send(
        self, request: httpx.Request, *, stream: bool = False, **kwargs: Any
    ) -> httpx.Response:
        method = (
            request.method
            if request.method
            in {"CONNECT", "DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE"}
            else "_OTHER"
        )
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


_database_histograms = {
    operation: metrics.get_meter("pycil.database").create_histogram(
        f"pycil.db.{operation}.duration",
        unit="s",
        description=description,
        explicit_bucket_boundaries_advisory=(
            0.001,
            0.005,
            0.01,
            0.025,
            0.05,
            0.1,
            0.25,
            0.5,
            1,
            2,
            5,
        ),
    )
    for operation, description in (
        (
            "pool.acquire",
            "Connection acquisition including queue, connection opening and validation",
        ),
        ("query", "SQLAlchemy cursor execution round trip, excluding pool acquisition"),
    )
}


@asynccontextmanager
async def telemetry(deployment: ProcessSettings, policy: TelemetryRuntime) -> AsyncGenerator[None]:
    global _telemetry_started
    if deployment.otel_endpoint is None:
        yield
        return
    # OTel global providers are set once; a new lifespan requires a new process.
    if _telemetry_started:
        raise RuntimeError("Telemetry already initialized; replace the API process")

    endpoint = deployment.otel_endpoint.rstrip("/")
    attributes = {
        "service.name": deployment.otel_service_name,
        "service.version": deployment.service_version,
        "deployment.environment.name": deployment.deployment_environment,
        "service.instance.id": str(uuid4()),
    }
    if deployment.git_sha:
        attributes["vcs.ref.head.revision"] = deployment.git_sha
    resource = Resource.create(attributes)
    _log_resource.update(
        {key: str(value) for key, value in attributes.items() if value is not None}
    )
    _log_resource["deployment.environment"] = str(deployment.deployment_environment)
    stack = ExitStack()
    try:
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(
                endpoint=f"{endpoint}/v1/metrics", timeout=policy.metrics.export_timeout_seconds
            ),
            export_interval_millis=policy.metrics.export_interval_seconds * 1000,
            export_timeout_millis=policy.metrics.export_timeout_seconds * 1000,
        )
        meter = MeterProvider(resource=resource, metric_readers=[reader], shutdown_on_exit=False)
        stack.callback(
            meter.shutdown, timeout_millis=policy.metrics.shutdown_timeout_seconds * 1000
        )
        tracer = TracerProvider(
            resource=resource,
            sampler=ParentBased(TraceIdRatioBased(deployment.otel_sample_ratio)),
            shutdown_on_exit=False,
            meter_provider=meter,
        )
        stack.callback(tracer.shutdown)
        tracer.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=f"{endpoint}/v1/traces", timeout=policy.traces.export_timeout_seconds
                ),
                max_queue_size=policy.traces.max_queue_size,
                max_export_batch_size=policy.traces.max_export_batch_size,
                schedule_delay_millis=policy.traces.schedule_delay_seconds * 1000,
                export_timeout_millis=policy.traces.export_timeout_seconds * 1000,
                meter_provider=meter,
            )
        )
        metrics.set_meter_provider(meter)
        trace.set_tracer_provider(tracer)
        _telemetry_started = True
        yield
    finally:
        # Native shutdown joins export workers; keep blocking work off the event loop.
        await asyncio.to_thread(stack.close)


class OperationOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


def record_database_duration(
    operation: Literal["pool.acquire", "query"],
    pool: Literal["application", "checkpoint"],
    started: float,
    error: BaseException | None = None,
) -> None:
    outcome = (
        OperationOutcome.SUCCEEDED
        if error is None
        else OperationOutcome.CANCELLED
        if isinstance(error, asyncio.CancelledError)
        else OperationOutcome.FAILED
    )
    _database_histograms[operation].record(
        perf_counter() - started, {"pool": pool, "outcome": outcome.value}
    )


@contextmanager
def observe_pool_acquisition(pool: Literal["application", "checkpoint"]) -> Generator[None]:
    started = perf_counter()
    error = None
    try:
        yield
    except BaseException as caught:
        error = caught
        raise
    finally:
        record_database_duration("pool.acquire", pool, started, error)


def configure_logging(
    log_format: str | None = None,
    log_level: str | int | None = None,
) -> None:
    """Configures structlog and standard library logging for unified output."""
    if log_format is None:
        env_format = os.getenv("LOG_FORMAT", "").strip().lower()
        if env_format in {"json", "console"}:
            log_format = env_format
        else:
            log_format = "console" if sys.stdout.isatty() else "json"

    level_map = logging.getLevelNamesMapping()
    if log_level is None:
        env_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        resolved_level = level_map.get(env_level, logging.INFO)
    elif isinstance(log_level, str):
        resolved_level = level_map.get(log_level.strip().upper(), logging.INFO)
    else:
        resolved_level = int(log_level)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        telemetry_context,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    if log_format == "json":

        def _orjson_serializer(record: object, **_: object) -> str:
            return orjson.dumps(record).decode()

        renderer: structlog.types.Processor = structlog.processors.JSONRenderer(
            serializer=_orjson_serializer
        )
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            structlog.stdlib.ExtraAdder(),
            *shared_processors,
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(resolved_level)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(resolved_level)

    # Route uvicorn loggers to root handler and delegate level filtering to root
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi"):
        sub_logger = logging.getLogger(logger_name)
        sub_logger.handlers.clear()
        sub_logger.propagate = True
        sub_logger.setLevel(logging.NOTSET)
    # Transport diagnostics include raw URLs; application boundaries own safe outcomes.
    for logger_name in ("httpx", "httpcore"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def telemetry_context(
    _logger: structlog.types.WrappedLogger, _method: str, event: structlog.types.EventDict
) -> structlog.types.EventDict:
    event.update(_log_resource)
    context = trace.get_current_span().get_span_context()
    if context.is_valid:
        event["trace_id"] = f"{context.trace_id:032x}"
        event["span_id"] = f"{context.span_id:016x}"
    else:
        event.pop("trace_id", None)
        event.pop("span_id", None)
    return event


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Returns a bound structlog logger."""
    return structlog.get_logger(name)


def bind_contextvars(**kwargs: object) -> None:
    """Binds key-values into async-local contextvars for all subsequent log events."""
    structlog.contextvars.bind_contextvars(**kwargs)


def bound_contextvars(**kwargs: object):
    """Context manager binding key-values into contextvars, unbinding on exit."""
    return structlog.contextvars.bound_contextvars(**kwargs)


def clear_contextvars() -> None:
    """Clears all bound contextvars for the current task/request."""
    structlog.contextvars.clear_contextvars()


def unbind_contextvars(*keys: str) -> None:
    """Unbinds specified keys from contextvars."""
    structlog.contextvars.unbind_contextvars(*keys)


@contextmanager
def observe_operation(
    logger: structlog.stdlib.BoundLogger, operation: str, **identifiers: object
) -> Generator[None]:
    """Correlate nested work and emit one sanitized outcome for its owning boundary."""
    started = perf_counter()
    outcome, category = OperationOutcome.SUCCEEDED, None
    with bound_contextvars(operation=operation, **identifiers):
        logger.info("operation_started")
        try:
            yield
        except BaseException as error:
            outcome = (
                OperationOutcome.CANCELLED
                if isinstance(error, asyncio.CancelledError)
                else OperationOutcome.FAILED
            )
            category = type(error).__name__
            raise
        finally:
            logger.info(
                "operation_completed",
                outcome=outcome,
                error_type=category,
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )
