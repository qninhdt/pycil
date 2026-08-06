"""Question supply warm-up: drive lexi's ``prepare_questions`` (not generation).

Supply is warmed per ``(sense_id, difficulty_level, expected_count)`` demand; the
API-side resolver later pulls concrete questions via ``retrieve_question``.  The
warm-up is best-effort — a failure to warm one sense/word never aborts the batch,
and the learner's ``/next`` simply defers until supply lands.

Two entry points, and the difference is who is listening. ``prepare_questions`` is
the warm-up itself. ``prepare_questions_task`` wraps it in the durable task
registry so its completion is *announced*: every transition writes an outbox row
that ``dispatch_task_outbox`` relays to ``async:{task_id}``, which is the only
channel shape the subscribe proxy admits. Without that the client's sole way to
learn supply had landed was to call ``/next`` again — and ``/next`` mutates.
"""

import logging
from collections import defaultdict
from uuid import UUID

from arq import Retry
from lexi_ai.contracts import PrepareDemand
from pycil.tasks.application import service as task_service
from pycil.tasks.infra.models import AsyncTaskStatus

logger = logging.getLogger(__name__)
_MAX_PREPARE_TRIES = 2


async def prepare_questions(ctx: dict, owner_uid: str, demands: list) -> dict:
    """Warm supply with bounded retries for transient reader/provider failures."""
    del owner_uid  # supply is per-word, not per-user
    reader = ctx["lexi_reader"]
    engine = ctx["lexi_engine"]
    failures = 0

    by_word: dict[int, list[PrepareDemand]] = defaultdict(list)
    for entry in demands:
        sense_id, level, count = int(entry[0]), int(entry[1]), int(entry[2])
        try:
            exposure = await reader.retrieve_exposure(sense_id)
        except LookupError:
            continue  # permanently missing/stale sense
        except Exception:
            failures += 1
            continue
        if exposure.word_id is None:
            continue
        by_word[int(exposure.word_id)].append(
            PrepareDemand(
                sense_id=str(sense_id),
                difficulty_level=level,
                expected_count=count,
            )
        )

    prepared = 0
    for word_id, word_demands in by_word.items():
        try:
            report = await engine.prepare_questions(word_id, word_demands)
            prepared += sum(report.produced.values())
        except Exception:
            failures += 1

    if failures:
        job_try = int(ctx.get("job_try", 1))
        if job_try < _MAX_PREPARE_TRIES:
            raise Retry(defer=5)
        logger.error(
            "question supply preparation exhausted",
            extra={"failed_groups": failures, "prepared": prepared},
        )
        return {"status": "failed", "prepared": prepared, "failed": failures}
    return {"status": "done", "prepared": prepared}


async def prepare_questions_task(
    ctx: dict, task_id: str, owner_uid: str, demands: list
) -> dict:
    """Warm supply under a durable task, so its completion can be subscribed to.

    The claim comes first and is what makes this idempotent: an arq retry, or the
    reconciler re-enqueueing a row whose original submission was lost, both land
    here and only one wins the fenced lease. The other returns ``duplicate``
    without re-running the warm-up, which is the expensive half.

    A settled transition is what the learner's client is waiting on, so both
    outcomes transition — including exhaustion. Leaving a failed warm-up in
    RUNNING would hang the session on a subscription that never resolves, which is
    strictly worse than the poll this replaces.
    """
    task_uuid = UUID(task_id)
    async with ctx["session_factory"]() as session:
        task = await task_service.claim_task(session, task_uuid, ctx.get("worker_id", "worker"))
    if task is None:
        return {"status": "duplicate"}

    try:
        outcome = await prepare_questions(ctx, owner_uid, demands)
    except Retry:
        # arq's own signal, not a failure: the task keeps its lease and this job is
        # redelivered. Transitioning here would settle a task still being worked.
        raise
    except Exception:
        logger.exception("question supply warm-up raised for task %s", task_id)
        async with ctx["session_factory"]() as session:
            updated = await task_service.transition_task(
                session,
                task_uuid,
                lease_token=task.lease_token,
                lease_fence=task.lease_fence,
                status=AsyncTaskStatus.FAILED,
                error_code="question_preparation_failed",
            )
        return {"status": "failed" if updated else "stale"}

    settled = AsyncTaskStatus.SUCCEEDED if outcome["status"] == "done" else AsyncTaskStatus.FAILED
    async with ctx["session_factory"]() as session:
        updated = await task_service.transition_task(
            session,
            task_uuid,
            lease_token=task.lease_token,
            lease_fence=task.lease_fence,
            status=settled,
            result={"prepared": outcome.get("prepared", 0)},
            error_code=(
                None if settled is AsyncTaskStatus.SUCCEEDED else "question_preparation_exhausted"
            ),
        )
    if not updated:
        return {"status": "stale"}
    return {"status": outcome["status"], "prepared": outcome.get("prepared", 0)}
