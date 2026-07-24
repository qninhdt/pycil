"""Question supply warm-up: drive lexi's ``prepare_questions`` (not generation).

Supply is warmed per ``(sense_id, difficulty_level, expected_count)`` demand; the
API-side resolver later pulls concrete questions via ``retrieve_question``.  The
warm-up is best-effort — a failure to warm one sense/word never aborts the batch,
and the learner's ``/next`` simply defers until supply lands.
"""

import logging
from collections import defaultdict
from uuid import UUID

from arq import Retry
from lexi_ai.contracts import PrepareDemand
from pycil.tasks import service as task_service
from pycil.tasks.models import AsyncTaskStatus

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


async def generate_question(
    ctx: dict,
    task_id: str,
    word_id: int,
    demands: list | None = None,
    n: int = 1,
    session_id: str | None = None,
    sense_id: int | None = None,
) -> dict:
    """Legacy task-keyed supply warm-up (drained via task reconciliation).

    Superseded by ``prepare_questions``; retained only to settle any in-flight
    ``question_pool`` task by warming that sense's supply through ``prepare``.
    """
    if sense_id is None:
        return {"status": "missing_sense", "questions": []}
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        task = await task_service.claim_task(session, UUID(task_id), ctx.get("worker_id", "worker"))
    if task is None:
        return {"status": "duplicate"}
    try:
        from pycil.learning.policy import ASSESSMENT_FLOOR

        demand = PrepareDemand(
            sense_id=str(sense_id),
            difficulty_level=ASSESSMENT_FLOOR,
            expected_count=n,
        )
        report = await ctx["lexi_engine"].prepare_questions(word_id, [demand])
        produced = sum(report.produced.values())
    except Exception:
        async with session_factory() as session:
            failed = await task_service.transition_task(
                session,
                UUID(task_id),
                lease_token=task.lease_token,
                lease_fence=task.lease_fence,
                status=AsyncTaskStatus.FAILED,
                error_code="question_generation_failed",
            )
        return {"status": "failed" if failed else "stale"}
    result = {"prepared": produced}
    async with session_factory() as session:
        completed = await task_service.complete_question_task(
            session,
            UUID(task_id),
            lease_token=task.lease_token,
            lease_fence=task.lease_fence,
            result=result,
        )
    return {"status": "done", **result} if completed else {"status": "stale"}
