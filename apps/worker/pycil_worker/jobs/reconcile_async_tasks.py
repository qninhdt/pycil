"""Restore durable task rows when their initial ARQ enqueue did not persist."""

import logging

from shared.tasks.contract import (
    JOB_NAME_FOR_KIND,
    TASK_KIND_GRADING,
    TASK_KIND_QUESTION_SUPPLY,
    TASK_KIND_WORD,
    GradingDispatch,
    SupplyDispatch,
    WordDispatch,
)

from pycil_worker.context import ReadyWorkerContext

logger = logging.getLogger(__name__)

# Table-driven dispatch: each kind maps to the typed parse of its stored
# payload, and the job name plus argument order come from the same contract
# objects the producers wrote with. A kind with no entry here lands in the
# `unknown` count below instead of being silently dropped.
_REENQUEUE_ARGS_FOR_KIND = {
    TASK_KIND_WORD: lambda dispatch: WordDispatch.from_dispatch(dispatch).job_args(),
    TASK_KIND_GRADING: lambda dispatch: GradingDispatch.from_dispatch(dispatch).job_args(),
    # The learner's client is subscribed to this task and nothing else — it
    # no longer re-asks `/next` while waiting. So a supply row whose enqueue
    # was lost is not a slow session, it is a stopped one, and this entry is
    # the whole backstop for that.
    TASK_KIND_QUESTION_SUPPLY: lambda dispatch: SupplyDispatch.from_dispatch(
        dispatch
    ).job_args(),
}


async def reconcile_async_tasks(ctx: ReadyWorkerContext) -> dict:
    from pycil.tasks.application import service as task_service

    async with ctx["session_factory"]() as session:
        tasks = await task_service.list_reenqueueable_tasks(session)

    reenqueued = 0
    unknown: dict[str, int] = {}
    for task in tasks:
        build_args = _REENQUEUE_ARGS_FOR_KIND.get(task.kind)
        if build_args is None:
            # An unhandled kind is silently unrecoverable: the row stays queued
            # forever and nothing surfaces it. Logged rather than raised, because one
            # unknown row must not stop the remaining tasks in the batch from being
            # re-enqueued. `question_pool` was such a kind until it was deleted, and
            # this branch is what makes the next one visible.
            unknown[task.kind] = unknown.get(task.kind, 0) + 1
            continue
        await ctx["redis"].enqueue_job(
            JOB_NAME_FOR_KIND[task.kind], str(task.id), *build_args(task.dispatch)
        )
        reenqueued += 1

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
