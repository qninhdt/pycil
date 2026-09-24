"""The word-generation use case: task registry, dispatch.

Both producers — the HTTP route and the assistant tool — call this function to
enqueue word generation guarded by singleflight and lexi reference caching.
"""

from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.queue.contracts import TASK_KIND_WORD, WordDispatch
from pycil.queue.receipts import enqueue_job


async def request_word_generation(
    session: AsyncSession,
    redis: Redis,
    *,
    owner_id: UUID,
    query: str,
    provenance: str,
    idempotency_key: str | None = None,
) -> UUID:
    """Publish one word-generation job and return its receipt id.

    The owner is recorded on the receipt so the status route can authorize a read;
    it is never taken from a client parameter.
    """
    del session, provenance, idempotency_key
    dispatch = WordDispatch(query=query, owner_id=str(owner_id))
    job_id = await enqueue_job(
        redis=redis,
        job_type=TASK_KIND_WORD,
        payload=dispatch.to_dispatch(),
        owner_id=str(owner_id),
    )
    return UUID(job_id)
