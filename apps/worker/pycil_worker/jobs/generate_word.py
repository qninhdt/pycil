"""generate_word_task: lazy dictionary generation (single-writer — worker only).

lexi-ai persists the entry to ITS OWN database and returns sense ids. pycil
stores no dictionary content. Guards an empty search by falling back to the
custom-string generate path.
"""

import logging
from uuid import UUID

from pycil.content.application import generation_quota
from pycil.tasks.application import service as task_service
from pycil.tasks.infra.models import AsyncTaskStatus

from pycil_worker.context import ReadyWorkerContext

logger = logging.getLogger(__name__)


async def generate_word_task(
    ctx: ReadyWorkerContext, task_id: str, query: str, owner_uid: str
) -> dict:
    """Generate one dictionary entry and settle its durable task.

    ``owner_uid`` identifies who was charged the inflight generation slot at
    submission. Both producers reserve two counters bounded by
    ``word_generation_max_inflight_per_user``; this job is what they enqueue, so
    it is the only place that can return them. Without the release, ten successful
    generations exhausted a learner's budget until the 900s TTL lapsed.

    Required, not optional. It defaulted to ``None`` so a job enqueued by a
    previous release would settle rather than raise ``TypeError`` mid rolling
    deploy — a queue that has never held such a job. Every producer and the
    reconciler pass it, so the default only hid a caller that forgot to.
    """
    task_uuid = UUID(task_id)
    owner_id = UUID(owner_uid)

    async def release() -> None:
        # Only a transition this worker actually won may return the slot: a
        # rejected fence means another attempt owns the task and is still charged
        # for it, so releasing here would let the learner exceed the bound.
        await generation_quota.release_inflight_quota(ctx["redis"], owner_id)

    async with ctx["session_factory"]() as session:
        task = await task_service.claim_task(session, task_uuid, ctx.get("worker_id", "worker"))
    if task is None:
        return {"status": "duplicate"}
    try:
        results = await ctx["lexi_reader"].search(query)
        entry = await ctx["lexi_engine"].generate_fenced(results[0] if results else query)
    except Exception:
        # Logged before it is recorded, because recording it loses it.
        # `transition_task` stores `word_generation_failed` and nothing else, so
        # the exception is the only account of *why* and it ends here. Without
        # this, explaining a live failure meant reproducing the call by hand
        # inside the container.
        logger.exception("generate_word_task failed for %r (task %s)", query, task_id)
        async with ctx["session_factory"]() as session:
            updated = await task_service.transition_task(
                session,
                task_uuid,
                lease_token=task.lease_token,
                lease_fence=task.lease_fence,
                status=AsyncTaskStatus.FAILED,
                error_code="word_generation_failed",
            )
        if updated is None:
            return {"status": "stale"}
        await release()
        return {"status": "failed"}
    result = {
        "wordId": entry.word_id,
        "senseIds": [sense.sense_id for sense in entry.senses if sense.sense_id is not None],
    }
    async with ctx["session_factory"]() as session:
        updated = await task_service.transition_task(
            session,
            task_uuid,
            lease_token=task.lease_token,
            lease_fence=task.lease_fence,
            status=AsyncTaskStatus.SUCCEEDED,
            result=result,
        )
    if updated is None:
        return {"status": "stale"}
    await release()
    return {"status": "succeeded", **result}
