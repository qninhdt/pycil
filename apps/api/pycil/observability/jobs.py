"""Use Taskiq's native tracing and measurements without another worker layer."""

from taskiq.middlewares.opentelemetry_middleware import (
    OpenTelemetryMiddleware as OpenTelemetryMiddleware,
)
