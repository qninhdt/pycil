from typing import Annotated, Self

from pydantic import Field, model_validator

from pycil.observability.config import TelemetryRuntime
from pycil.utils.configuration import NonnegativeInt, Policy, PositiveInt

PositiveSeconds = Annotated[float, Field(strict=True, gt=0)]


class CachePolicy(Policy):
    ttl_seconds: PositiveInt
    max_entries: PositiveInt


class CachesPolicy(Policy):
    user_id: CachePolicy
    words: CachePolicy
    senses: CachePolicy
    artifacts: CachePolicy


class ApplicationPool(Policy):
    size: PositiveInt
    max_overflow: NonnegativeInt
    timeout_seconds: PositiveSeconds
    connect_timeout_seconds: PositiveSeconds


class CheckpointPool(Policy):
    min_size: NonnegativeInt
    max_size: PositiveInt
    timeout_seconds: PositiveSeconds
    startup_timeout_seconds: PositiveSeconds

    @model_validator(mode="after")
    def pool_bounds(self) -> Self:
        if self.min_size > self.max_size:
            raise ValueError("pool minimum exceeds maximum")
        return self


class DatabaseRuntime(Policy):
    application_pool: ApplicationPool
    checkpoint_pool: CheckpointPool


class RedisRuntime(Policy):
    connect_timeout_seconds: PositiveSeconds
    operation_timeout_seconds: PositiveSeconds
    max_connections: PositiveInt


class HTTPRuntime(Policy):
    max_body_bytes: PositiveInt
    client_timeout_seconds: PositiveSeconds


class HealthRuntime(Policy):
    timeout_seconds: PositiveSeconds
    redis_timeout_seconds: PositiveSeconds


class LifecycleRuntime(Policy):
    cleanup_timeout_seconds: PositiveSeconds


class SystemConfig(Policy):
    database: DatabaseRuntime
    redis: RedisRuntime
    http: HTTPRuntime
    health: HealthRuntime
    lifecycle: LifecycleRuntime
    telemetry: TelemetryRuntime
    caches: CachesPolicy
