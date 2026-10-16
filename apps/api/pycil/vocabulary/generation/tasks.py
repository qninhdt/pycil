"""Vocabulary submission policy and an ordinary native Taskiq task."""

from typing import cast
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.contextvars import bound_contextvars
from taskiq import AsyncBroker, Context, SendTaskError, TaskiqDepends
from taskiq.depends.progress_tracker import ProgressTracker, TaskState
from taskiq_redis.exceptions import ResultIsMissingError

from pycil.account.models import User
from pycil.app.broker import RetryableJobError, broker
from pycil.app.config import AppConfig
from pycil.app.http import Problem
from pycil.app.resources import WorkerResources
from pycil.jobs.metadata import owned, owner_key
from pycil.jobs.schemas import Accepted
from pycil.jobs.singleflight import singleflight
from pycil.utils.hashing import sha256_hex
from pycil.vocabulary.errors import InvalidHandleError
from pycil.vocabulary.generation.pipeline import generate_word
from pycil.vocabulary.references.reference import fetch_reference


def word_request_key(user: UUID | str, fingerprint: str) -> str:
    return f"pycil:vocabulary:request:{user}:{fingerprint}"


def word_generation_lock_key(reference_id: str) -> str:
    return f"pycil:vocabulary:generation:lock:{reference_id}"


async def request_generation(
    sessions: async_sessionmaker[AsyncSession],
    redis: Redis,
    native: AsyncBroker,
    config: AppConfig,
    user: UUID,
    reference_id: str,
) -> Accepted:
    try:
        await fetch_reference(sessions, reference_id)
    except InvalidHandleError:
        raise Problem(422, "invalid_reference") from None
    fingerprint = sha256_hex(
        reference_id
        + config.product.vocabulary.generation.model_dump_json()
        + config.runtime.providers.vocabulary.model_dump_json()
    )
    key = word_request_key(user, fingerprint)
    ttl = config.runtime.jobs.result_ttl_seconds
    try:
        async with singleflight(redis, native, key, user) as existing:
            if existing:
                return Accepted.for_job(existing)
            job_id = native.id_generator()
            await redis.set(owner_key(job_id), str(user), ex=ttl)
            await (
                generate_word_task.kicker()
                .with_broker(native)
                .with_task_id(job_id)
                .with_labels(
                    timeout=config.runtime.jobs.timeout_seconds,
                )
                .kiq(user_id=str(user), reference_id=reference_id)
            )
            await redis.set(key, job_id, pxat=await redis.pexpiretime(owner_key(job_id)))
            return Accepted.for_job(job_id)
    except RedisError, SendTaskError, TimeoutError:
        # Publish may have succeeded: ownership deliberately remains until expiry.
        raise Problem(503, "job_submission_unavailable") from None


@broker.task(task_name="vocabulary.generate_word", retry_on_error=True, max_retries=2)
async def generate_word_task(
    user_id: str,
    reference_id: str,
    context: Context = TaskiqDepends(),
    progress: ProgressTracker = TaskiqDepends(),
) -> dict[str, int]:
    resources = cast(WorkerResources, context.state.resources)
    config = cast(AppConfig, context.state.config)
    with bound_contextvars(task_id=context.message.task_id):
        try:
            try:
                if not await owned(resources.redis, context.message.task_id, UUID(user_id)):
                    raise RuntimeError("job_expired")
                try:
                    result = await context.broker.result_backend.get_result(context.message.task_id)
                except ResultIsMissingError:
                    pass
                else:
                    if not result.is_err:
                        return result.return_value
                async with resources.sessions() as session:
                    if (
                        await session.scalar(select(User.id).where(User.id == UUID(user_id)))
                        is None
                    ):
                        raise RuntimeError("account_not_found")
                await progress.set_progress(TaskState.STARTED)
            except ConnectionError, RedisConnectionError, RedisTimeoutError, OperationalError:
                raise RetryableJobError("job_dependencies_unavailable") from None
            async with resources.redis.lock(
                word_generation_lock_key(reference_id),
                timeout=config.runtime.jobs.lock_timeout_seconds,
                blocking_timeout=config.runtime.jobs.timeout_seconds,
                thread_local=False,
                raise_on_release_error=False,
            ):
                word = await generate_word(
                    resources.sessions,
                    resources.structured_llm,
                    resources.word_store,
                    reference_id=reference_id,
                    example_count=config.product.vocabulary.generation.examples_per_sense,
                    enrichment_batch_size=config.runtime.generation.enrichment_batch_size,
                    sense_store=resources.sense_store,
                )
                return {"word_id": word.id}
        except RetryableJobError:
            raise
        except Exception:
            # Native Taskiq logs/serializes exceptions; provider payloads must not escape.
            raise RuntimeError("word_generation_failed") from None
