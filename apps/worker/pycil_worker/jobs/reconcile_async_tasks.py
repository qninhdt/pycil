"""Restore durable task rows when their initial ARQ enqueue did not persist."""

import logging

logger = logging.getLogger(__name__)


async def reconcile_async_tasks(ctx: dict) -> dict:
    from pycil.tasks import service as task_service

    async with ctx["session_factory"]() as session:
        tasks = await task_service.list_reenqueueable_tasks(session)

    reenqueued = 0
    unknown: dict[str, int] = {}
    for task in tasks:
        dispatch = task.dispatch
        if task.kind == "word":
            # `owner_id` is absent on rows written by the previous release; the job
            # treats it as optional and settles without releasing a slot it cannot
            # attribute.
            await ctx["redis"].enqueue_job(
                "generate_word_task", str(task.id), dispatch["query"], dispatch.get("owner_id")
            )
            reenqueued += 1
        elif task.kind == "grading":
            await ctx["redis"].enqueue_job(
                "grade_answer_task", str(task.id), dispatch["owner_id"], dispatch["response_id"]
            )
            reenqueued += 1
        else:
            # An unhandled kind is silently unrecoverable: the row stays queued
            # forever and nothing surfaces it. Logged rather than raised, because one
            # unknown row must not stop the remaining tasks in the batch from being
            # re-enqueued. `question_pool` was such a kind until it was deleted, and
            # this branch is what makes the next one visible.
            unknown[task.kind] = unknown.get(task.kind, 0) + 1

    if unknown:
        logger.error(
            "async task kinds with no re-enqueue handler",
            extra={"kinds": unknown},
        )
    return {
        "status": "reconciled",
        "count": reenqueued,
        "unhandled": sum(unknown.values()),
    }
