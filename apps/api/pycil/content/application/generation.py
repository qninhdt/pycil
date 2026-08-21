"""The word-generation use case: quota, task registry, dispatch.

Both producers — the HTTP route and the assistant tool — ran their own copy of
reserve → submit → release → enqueue, and the copies had drifted. This is the
one application function both call; the only thing that differs between them
arrives as parameters (provenance, idempotency key), never as a second pipeline.
"""

from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.common.errors import TooManyRequestsError
from pycil.config import settings
from pycil.content.application import generation_quota
from pycil.tasks.application.dispatch import submit_and_dispatch
from pycil.tasks.domain.vocabulary import TASK_KIND_WORD, WordDispatch
from pycil.tasks.domain.work_keys import word_work_key


async def request_word_generation(
    session: AsyncSession,
    redis: Redis,
    *,
    owner_id: UUID,
    query: str,
    provenance: str,
    idempotency_key: str | None = None,
) -> UUID:
    """Charge the quota, submit or join the durable word task, wake a worker.

    Returns the committed task id, which is what every producer hands back: the
    client subscribes to ``async:{task_id}`` for the outcome.

    ``provenance`` records who asked ("word-search" from the route, "assistant"
    from the tool) while the work key joins them onto one shared task for one
    word — same row, two interests.

    The quota reservation is rolled back when the submission fails or joins
    existing work: a join reserved a slot it never spends, and without the
    rollback repeatedly asking for a word already being generated would exhaust
    the learner's inflight budget until the 900s TTL lapsed.
    """
    if not await generation_quota.reserve_quota(redis, owner_id):
        # Kept as an existing domain exception until the API-wide 429 mapping lands.
        raise TooManyRequestsError(
            "word_generation_quota_exceeded",
            code="word_generation_quota_exceeded",
            retry_after=3600,
        )
    submission = await submit_and_dispatch(
        session,
        kind=TASK_KIND_WORD,
        server_work_key=word_work_key(
            generation_quota.normalize_query(query),
            settings.lexi_reference_dataset_fingerprint,
        ),
        requester_id=owner_id,
        command_kind="word.generate",
        command_id=idempotency_key or f"word:{uuid4()}",
        provenance=provenance,
        dispatch=WordDispatch(query=query, owner_id=str(owner_id)),
        release_reservation=lambda: generation_quota.release_inflight_quota(redis, owner_id),
    )
    return submission.task.id
