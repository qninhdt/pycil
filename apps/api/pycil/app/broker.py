"""Native Taskiq configuration; the Taskiq CLI owns worker execution."""

from contextlib import AsyncExitStack
from uuid import uuid7

from taskiq import TaskiqEvents, TaskiqState, async_shared_broker
from taskiq.middlewares import SimpleRetryMiddleware
from taskiq.serializers import JSONSerializer
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from pycil.app.config import AppConfig, load_config
from pycil.app.settings import ProcessSettings, WorkerSettings
from pycil.observability import configure_logging
from pycil.observability.jobs import OpenTelemetryMiddleware

TASK_STREAM_KEY = "pycil:jobs:tasks"
CONSUMER_GROUP_NAME = "pycil-workers"
TASK_RESULT_PREFIX = "pycil:jobs:result"

# Taskiq's shared broker registers tasks without loading configuration or connecting.
broker = async_shared_broker


class RetryableJobError(RuntimeError):
    """A safe infrastructure failure before domain side effects or paid calls."""


def create_broker(config: AppConfig, deployment: ProcessSettings) -> RedisStreamBroker:
    redis = config.system.redis
    native = (
        RedisStreamBroker(
            deployment.redis_url.get_secret_value(),
            queue_name=TASK_STREAM_KEY,
            consumer_group_name=CONSUMER_GROUP_NAME,
            consumer_id="0",
            xread_block=int(min(2, redis.operation_timeout_seconds / 2) * 1000),
            xread_count=1,
            idle_timeout=max(600_000, config.jobs.timeout_seconds * 2_000),
            unacknowledged_lock_timeout=10,
            max_connection_pool_size=redis.max_connections,
            socket_connect_timeout=redis.connect_timeout_seconds,
            socket_timeout=redis.operation_timeout_seconds,
        )
        .with_id_generator(lambda: str(uuid7()))
        .with_result_backend(
            RedisAsyncResultBackend[object](
                redis_url=deployment.redis_url.get_secret_value(),
                prefix_str=TASK_RESULT_PREFIX,
                result_ex_time=config.jobs.result_ttl_seconds,
                keep_results=True,
                serializer=JSONSerializer(),
                max_connection_pool_size=redis.max_connections,
                socket_connect_timeout=redis.connect_timeout_seconds,
                socket_timeout=redis.operation_timeout_seconds,
            )
        )
        .with_middlewares(
            SimpleRetryMiddleware(
                default_retry_count=2,
                default_retry_label=False,
                no_result_on_retry=True,
                types_of_exceptions=(RetryableJobError,),
            )
        )
    )
    broker.default_broker(native)
    return native


def worker_broker() -> RedisStreamBroker:
    """Native CLI broker factory, called inside each worker process."""
    configure_logging()
    config = load_config()
    deployment = WorkerSettings.from_environment()
    native = create_broker(config, deployment)

    @native.on_event(TaskiqEvents.WORKER_STARTUP)
    async def startup(state: TaskiqState) -> None:
        from pycil.app.resources import worker_resources

        stack = AsyncExitStack()
        try:
            state.resources = await stack.enter_async_context(worker_resources(config, deployment))
            state.config = config
            native.add_middlewares(OpenTelemetryMiddleware())
        except BaseException:
            await stack.aclose()
            raise
        state.resources_stack = stack

    @native.on_event(TaskiqEvents.WORKER_SHUTDOWN)
    async def shutdown(state: TaskiqState) -> None:
        await state.resources_stack.aclose()

    return native
