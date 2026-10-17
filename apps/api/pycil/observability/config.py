"""Telemetry inputs; environment loading belongs to application composition."""

from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from pycil.utils.configuration import Policy, PositiveInt

PositiveSeconds = Annotated[float, Field(strict=True, gt=0)]


class TelemetrySettings(Policy):
    otel_endpoint: str | None = None
    otel_service_name: str = Field(min_length=1)
    service_version: str | None = None
    git_sha: str | None = None
    deployment_environment: Literal["local", "vps", "aws"] | None = None
    otel_sample_ratio: float = Field(default=0.1, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_telemetry(self):
        if self.otel_endpoint is not None:
            endpoint = urlsplit(self.otel_endpoint)
            if (
                endpoint.scheme not in {"http", "https"}
                or not endpoint.hostname
                or endpoint.username
                or endpoint.password
                or endpoint.query
                or endpoint.fragment
            ):
                raise ValueError("OTLP endpoint must be HTTP(S) without credentials/query/fragment")
            if not self.service_version or not self.service_version.strip():
                raise ValueError("OTLP export requires an immutable SERVICE_VERSION")
            if self.deployment_environment is None:
                raise ValueError("OTLP export requires DEPLOYMENT_ENVIRONMENT")
        return self


class TracesRuntime(Policy):
    max_queue_size: PositiveInt
    max_export_batch_size: PositiveInt
    schedule_delay_seconds: PositiveSeconds
    export_timeout_seconds: PositiveSeconds

    @model_validator(mode="after")
    def batch_bounds(self):
        if self.max_export_batch_size > self.max_queue_size:
            raise ValueError("trace export batch exceeds queue capacity")
        return self


class MetricsRuntime(Policy):
    export_interval_seconds: PositiveSeconds
    export_timeout_seconds: PositiveSeconds
    shutdown_timeout_seconds: PositiveSeconds


class TelemetryRuntime(Policy):
    traces: TracesRuntime
    metrics: MetricsRuntime
