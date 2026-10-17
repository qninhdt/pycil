"""Study submission policy and a native Taskiq preparation task."""

from collections.abc import Mapping
from typing import cast
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.contextvars import bound_contextvars
from taskiq import AsyncBroker, Context, SendTaskError, TaskiqDepends
from taskiq.depends.progress_tracker import ProgressTracker, TaskState
from taskiq_redis.exceptions import ResultIsMissingError

from pycil.account.config import PlanPolicy
from pycil.account.plans import Plan
from pycil.app.broker import RetryableJobError, broker
from pycil.app.resources import WorkerResources
from pycil.jobs.config import JobsConfig
from pycil.jobs.metadata import owned, owner_key
from pycil.jobs.schemas import Accepted
from pycil.jobs.singleflight import singleflight
from pycil.library.access import readable
from pycil.study.config import LearningPreferences, StudyConfig
from pycil.study.enums import Selection
from pycil.study.preparation import normalize_preparation, prepare
from pycil.study.schemas import Preparation, Prepare
from pycil.utils.errors import Unavailable
from pycil.utils.hashing import sha256_hex


def study_request_key(user: UUID | str, fingerprint: str) -> str:
    return f"pycil:study:request:{user}:{fingerprint}"


async def request_preparation(
    sessions: async_sessionmaker[AsyncSession],
    redis: Redis,
    native: AsyncBroker,
    study_config: StudyConfig,
    jobs_config: JobsConfig,
    user: UUID,
    data: Prepare,
    *,
    plans: Mapping[Plan, PlanPolicy],
) -> Accepted:
    async with sessions() as session:
        preferences = await normalize_preparation(
            session,
            user,
            study_config,
            selection=data.selection,
            max_sense_count=data.max_sense_count,
            questions_per_sense=data.questions_per_sense,
            plans=plans,
        )
        async with session.begin():
            await readable(session, data.node_id, user)
    fingerprint = sha256_hex(
        str(data.node_id)
        + data.selection
        + preferences.model_dump_json()
        + study_config.model_dump_json()
    )
    key = study_request_key(user, fingerprint)
    ttl = jobs_config.result_ttl_seconds
    try:
        async with singleflight(redis, native, key, user) as existing:
            if existing:
                return Accepted.for_job(existing)
            job_id = native.id_generator()
            await redis.set(owner_key(job_id), str(user), ex=ttl)
            selection_val = data.selection.value
            await (
                prepare_task.kicker()
                .with_broker(native)
                .with_task_id(job_id)
                .with_labels(
                    timeout=jobs_config.timeout_seconds,
                )
                .kiq(
                    user_id=str(user),
                    node_id=str(data.node_id),
                    selection=selection_val,
                    preferences=preferences.model_dump(mode="json"),
                )
            )
            await redis.set(key, job_id, pxat=await redis.pexpiretime(owner_key(job_id)))
            return Accepted.for_job(job_id)
    except RedisError, SendTaskError, TimeoutError:
        raise Unavailable("job_submission_unavailable") from None


@broker.task(task_name="study.prepare", retry_on_error=True, max_retries=2)
async def prepare_task(
    user_id: str,
    node_id: str,
    selection: str,
    preferences: dict[str, object],
    context: Context = TaskiqDepends(),
    progress: ProgressTracker[object] = TaskiqDepends(),
) -> dict[str, object]:
    resources = cast(WorkerResources, context.state.resources)
    config = context.state.config
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
                    raw_return: object = result.return_value
                    if not result.is_err and isinstance(raw_return, dict):
                        return cast(dict[str, object], raw_return)
                async with resources.sessions() as session:
                    normalized = await normalize_preparation(
                        session,
                        UUID(user_id),
                        config.study,
                        selection=Selection(selection),
                        preferences=LearningPreferences.model_validate(preferences),
                        plans=config.account.plans,
                    )
                await progress.set_progress(TaskState.STARTED)
            except ConnectionError, RedisConnectionError, RedisTimeoutError, OperationalError:
                raise RetryableJobError("job_dependencies_unavailable") from None
            async with resources.sessions() as session:
                result = await prepare(
                    session,
                    resources.sessions,
                    resources.structured_llm,
                    resources.artifact_store,
                    UUID(user_id),
                    UUID(node_id),
                    config.study,
                    selection=Selection(selection),
                    preferences=normalized,
                    sense_store=resources.sense_store,
                    library_config=config.library,
                    generation_batch_size=config.study.artifacts.batch_size,
                )
            return Preparation.model_validate(result).model_dump(mode="json")
        except RetryableJobError:
            raise
        except Exception:
            raise RuntimeError("study_preparation_failed") from None
