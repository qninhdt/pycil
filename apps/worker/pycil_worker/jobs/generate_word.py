"""generate_word: lazy dictionary generation (single-writer — worker only).

lexi-ai persists the entry to ITS OWN database and returns sense ids. pycil
stores no dictionary content. Guards an empty search by falling back to the
custom-string generate path.
"""

from uuid import UUID

from pycil.tasks import service as task_service
from pycil.tasks.models import AsyncTaskStatus

from pycil_worker import realtime


async def generate_word(ctx: dict, owner_uid: str, query: str, generation_id: str) -> dict:
    reader = ctx["lexi_reader"]
    worker_engine = ctx["lexi_engine"]
    session_factory = ctx["session_factory"]

    from pycil.jobs import service as jobs_service

    async with session_factory() as session:
        record = await jobs_service.claim_generation(
            session,
            UUID(generation_id),
            ctx.get("worker_id", "worker"),
            redis=ctx.get("redis"),
        )
    if record is None:
        return {"status": "duplicate"}

    await realtime.publish_job(owner_uid, generation_id, "running")

    try:
        results = await reader.search(query)
        # Empty-search guard: no Cambridge/generated hit → custom-string generate.
        source = results[0] if results else query
        entry = await worker_engine.generate_fenced(source)
    except Exception:
        async with session_factory() as session:
            completed = await jobs_service.fail_generation(
                session,
                UUID(generation_id),
                record.lease_token,
                record.lease_fence,
                "generation_failed",
            )
        if completed is None:
            return {"status": "stale"}
        status_val = getattr(completed.status, "value", completed.status)
        if status_val == "failed":
            await jobs_service.release_inflight_quota(ctx["redis"], completed.owner_id)
            await realtime.publish_job(owner_uid, generation_id, "failed")
            return {"status": "failed"}
        await realtime.publish_job(owner_uid, generation_id, "queued")
        return {"status": "retry_scheduled"}

    sense_ids = [s.sense_id for s in entry.senses if s.sense_id is not None]
    result = {"wordId": entry.word_id, "senseIds": sense_ids}
    async with session_factory() as session:
        completed = await jobs_service.complete_generation(
            session, UUID(generation_id), record.lease_token, record.lease_fence, result
        )
    if completed is None:
        return {"status": "stale"}
    await jobs_service.release_inflight_quota(ctx["redis"], completed.owner_id)
    await realtime.publish_job(owner_uid, generation_id, "succeeded", detail=entry.display)
    # pycil stores nothing here — the ids belong to lexi's DB.
    return {"status": "succeeded", **result}


async def generate_word_task(ctx: dict, task_id: str, query: str) -> dict:
    """Complete the SSE task resource while retaining the legacy handler above."""
    task_uuid = UUID(task_id)
    async with ctx["session_factory"]() as session:
        task = await task_service.claim_task(session, task_uuid, ctx.get("worker_id", "worker"))
    if task is None:
        return {"status": "duplicate"}
    try:
        results = await ctx["lexi_reader"].search(query)
        entry = await ctx["lexi_engine"].generate_fenced(
            results[0] if results else query
        )
    except Exception:
        async with ctx["session_factory"]() as session:
            updated = await task_service.transition_task(
                session, task_uuid, lease_token=task.lease_token, lease_fence=task.lease_fence,
                status=AsyncTaskStatus.FAILED, error_code="word_generation_failed",
            )
        return {"status": "failed" if updated else "stale"}
    result = {
        "wordId": entry.word_id,
        "senseIds": [sense.sense_id for sense in entry.senses if sense.sense_id is not None],
    }
    async with ctx["session_factory"]() as session:
        updated = await task_service.transition_task(
            session, task_uuid, lease_token=task.lease_token, lease_fence=task.lease_fence,
            status=AsyncTaskStatus.SUCCEEDED, result=result,
        )
    return {"status": "succeeded", **result} if updated else {"status": "stale"}
