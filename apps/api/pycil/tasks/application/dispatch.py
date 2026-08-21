"""The submit-and-dispatch choreography, stated once.

Reserve → ``submit_or_join`` → release on failure or join → best-effort enqueue
was copy-pasted at every producer and the copies had already drifted in
error-handling shape. The choreography is fixed here (Template Method via
composition: the varying step arrives as a hook, not a subclass); producers
supply domain parameters and, when their reservation must be given back, a
release callable.
"""

from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pycil.db.redis import get_arq_pool
from pycil.tasks.application import service as task_service
from pycil.tasks.domain.vocabulary import (
    JOB_NAME_FOR_KIND,
    GradingDispatch,
    SupplyDispatch,
    WordDispatch,
)


async def submit_and_dispatch(
    session: AsyncSession,
    *,
    kind: str,
    server_work_key: str,
    requester_id: UUID,
    command_kind: str,
    command_id: str,
    provenance: str,
    dispatch: WordDispatch | GradingDispatch | SupplyDispatch,
    release_reservation: Callable[[], Awaitable[None]] | None = None,
) -> task_service.TaskSubmission:
    """Submit (or join) the durable task, then wake a worker best-effort.

    The job name comes from the shared kind registry and the handler arguments
    from the typed payload, so a producer cannot enqueue under a name the worker
    does not register or in an argument order the handler does not read.

    ``release_reservation`` is what a producer must give back when its charge did
    NOT become durably spent: a failed submission, or a join of work another
    caller already paid for. Producers whose charge is legitimately spent once
    their pending row exists omit it.
    """
    try:
        submission = await task_service.submit_or_join(
            session,
            kind=kind,
            server_work_key=server_work_key,
            requester_id=requester_id,
            command_kind=command_kind,
            command_id=command_id,
            provenance=provenance,
            dispatch=dispatch,
        )
    except Exception:
        if release_reservation is not None:
            await release_reservation()
        raise
    if submission.task_created:
        await _best_effort_enqueue(
            JOB_NAME_FOR_KIND[kind], submission.task.id, dispatch.job_args()
        )
    elif release_reservation is not None:
        await release_reservation()
    return submission


async def _best_effort_enqueue(job_name: str, task_id: UUID, job_args: tuple) -> None:
    """Enqueue the wake-up job, tolerating an unreachable queue.

    The task row is already committed here, so ``reconcile_async_tasks``
    re-enqueues anything whose ARQ submission was lost: a failure costs latency,
    never the work. Swallowed on purpose — there is nothing a caller could do
    with this error that the reconciler does not already do.
    """
    try:
        pool = await get_arq_pool()
        await pool.enqueue_job(job_name, str(task_id), *job_args)
    except Exception:
        # Durable reconciliation handles enqueue outages; see docstring above.
        pass
