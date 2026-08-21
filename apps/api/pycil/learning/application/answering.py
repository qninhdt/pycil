"""Answer submission: bind, evaluate, and apply or defer the consequence.

Extracted from a 190-line route whose `try` block spanned 143 lines. The shape is
kept deliberately: one `try` around everything after the consume-once bind, because
the compensation it performs is the only thing that stops a failed answer stranding a
sense for the rest of the session.

Decomposed by the actual branches rather than by line count:

- `_bind`          everything that must succeed before the learner is committed to
                   anything — the question exists, is assessable, and is the sense's
                   currently delivered checkpoint.
- `_apply_now`     a rule type: the verdict exists, so apply FSRS and return it.
- `_defer`         an LLM type: no verdict yet, so charge the quota, write a durable
                   pending row and hand off to the worker.

The three-valued compensation is stated as an enum instead of two booleans, because
"neither" is a real case with its own behaviour and a pair of flags makes that the
absence of information rather than a decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID

from lexi_ai.contracts import PresentedQuestion
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.schemas import CurrentUser
from pycil.common.errors import ConflictError
from pycil.db.redis import get_arq_pool
from pycil.learning.application import service
from pycil.learning.application.question_delivery import render_format
from pycil.learning.domain import grading
from pycil.learning.infra import session_store
from pycil.learning.infra.models import Response
from pycil.ports.lexi import LexiReader
from pycil.tasks.application import service as task_service
from pycil.tasks.domain.vocabulary import JOB_NAME_FOR_KIND, TASK_KIND_GRADING, GradingDispatch
from pycil.tasks.domain.work_keys import grading_work_key


class _Claim(Enum):
    """What a failure after the bind must do to the delivery.

    ``OPEN``       nothing is claimed: release it, so the sense returns in a later
                   round rather than being stranded.
    ``BIND_HELD``  nothing was written *and* the same question is still the one to
                   answer, so the bind must survive for a retry to work at all.
    ``COMMITTED``  a durable row exists, so reopening would let a retry double-insert
                   it and pay for a second LLM grade.
    """

    OPEN = "open"
    BIND_HELD = "bind_held"
    COMMITTED = "committed"


class _ClaimState:
    """A mutable holder for the claim, so it can be raised through a failure.

    Deliberately not a return value. The claim exists *for* the failure path, and a
    returned value only ever arrives on the success path — an earlier version of this
    module had `_defer` return it, which meant an exception raised after the pending
    row was committed left the caller still believing nothing was claimed. It then
    reopened a delivery whose grade was already durable, so the learner could be
    handed the very checkpoint a worker was being paid to grade.

    Mutating a holder at the exact statement that changes the durable state keeps the
    flag and the fact it describes inseparable.
    """

    __slots__ = ("value",)

    def __init__(self) -> None:
        self.value = _Claim.OPEN


@dataclass(frozen=True)
class GradedNow:
    """A rule type: the verdict is known and already applied."""

    response_id: UUID
    sense_id: int
    render_format: str
    is_correct: bool
    grade_score: float | None
    grade_feedback: str | None
    reveal: dict | None
    mastery_before: int | None
    mastery_after: int | None


@dataclass(frozen=True)
class Deferred:
    """An LLM type: a durable pending row exists and a worker owns the verdict."""

    response_id: UUID
    sense_id: int
    render_format: str
    task_id: UUID


SubmitOutcome = GradedNow | Deferred


@dataclass(frozen=True)
class _Bound:
    question: PresentedQuestion
    sense_id: int
    requested_level: int
    served_level: int
    render_format: str


async def submit(
    session: AsyncSession,
    redis: Redis,
    client: LexiReader,
    *,
    user: CurrentUser,
    session_id: str,
    question_id: int,
    answer: str,
    now: datetime,
) -> SubmitOutcome:
    """Grade one answer, synchronously or by deferral.

    The caller has already authorized the session and its scope.
    """
    question, sense_id = await _resolve_question(
        redis, client, session_id=session_id, question_id=question_id
    )

    # Consume-once bind: the submitted question must be the sense's currently
    # delivered checkpoint; a replayed or self-selected id is rejected.
    if not await session_store.consume_delivered(
        redis, session_id, sense_id, question_id
    ):
        raise ConflictError("question_not_issued_for_session")

    claim = _ClaimState()
    try:
        bound = await _bind(
            redis,
            question=question,
            sense_id=sense_id,
            session_id=session_id,
        )
        evaluation = await client.evaluate_answer(
            question_id, grading.answer_submission(question, answer)
        )
        if evaluation is None:
            raise ConflictError("question_not_assessable")

        if evaluation.status == "graded":
            outcome = await _apply_now(
                session,
                redis,
                user=user,
                session_id=session_id,
                question_id=question_id,
                bound=bound,
                evaluation=evaluation,
                now=now,
            )
            # The verdict is durably applied; a later failure must NOT re-arm the
            # consume-once bind (that would let a retry double-insert the row).
            claim.value = _Claim.COMMITTED
            return outcome

        return await _defer(
            session,
            redis,
            user=user,
            session_id=session_id,
            question_id=question_id,
            bound=bound,
            answer=answer,
            claim=claim,
        )
    except Exception:
        # Reopen the delivery so the sense stays reachable — but only when nothing was
        # claimed. `COMMITTED` means a durable row exists, so reopening would let a
        # retry double-insert it; `BIND_HELD` means nothing was written *and* the same
        # question is still the one to answer, so the binding must survive for the
        # retry to work at all. Everything else is a genuine abort.
        if claim.value is _Claim.OPEN:
            await session_store.restore_delivered(
                redis, session_id, sense_id, question_id
            )
        raise


async def _resolve_question(
    redis: Redis,
    client: LexiReader,
    *,
    session_id: str,
    question_id: int,
) -> tuple[PresentedQuestion, int]:
    """Fetch the authoritative question and its sense, or reject and reopen.

    ``/answers`` takes only a question id and an answer, never a client-supplied
    question payload: the server re-fetches what it issued and grades that, which is
    what makes answer-key tampering impossible.

    Both rejections here happen BEFORE ``consume_delivered``, so nothing has released
    the bind — and in the purged case the learner can never resubmit that id, so the
    checkpoint has to be reopened or the sense is undeliverable for the rest of the
    session.
    """
    question = await client.get_question(question_id)
    sense_id: int | None = None
    if question is not None and question.sense_id is not None:
        try:
            sense_id = int(question.sense_id)
        except (TypeError, ValueError):
            sense_id = None
    if question is None or sense_id is None:
        # A purged or regenerated question is a conflict, not a server failure.
        await session_store.reopen_bound_delivery(redis, session_id, question_id)
        raise ConflictError("question_not_available")
    if question.interaction != "assessment":
        await session_store.reopen_bound_delivery(redis, session_id, question_id)
        raise ConflictError("question_not_assessable")
    return question, sense_id


async def _bind(
    redis: Redis,
    *,
    question: PresentedQuestion,
    sense_id: int,
    session_id: str,
) -> _Bound:
    """Resolve the levels this answer is recorded against.

    ``requested_level`` comes from the checkpoint, not from the question: a retry must
    be scored against the level it was originally asked at, even when supply forced a
    fallback to an easier question.
    """
    progress = await session_store.get_progress(redis, session_id, sense_id)
    if progress is None:
        raise ConflictError("question_not_issued_for_session")
    if progress.open_checkpoint is not None:
        requested_level = progress.open_requested_level
    elif progress.passed < len(progress.requested_levels):
        requested_level = progress.requested_levels[progress.passed]
    else:
        requested_level = question.difficulty_level
    return _Bound(
        question=question,
        sense_id=sense_id,
        requested_level=requested_level,
        served_level=question.difficulty_level,
        render_format=render_format(question),
    )


async def _apply_now(
    session: AsyncSession,
    redis: Redis,
    *,
    user: CurrentUser,
    session_id: str,
    question_id: int,
    bound: _Bound,
    evaluation,
    now: datetime,
) -> GradedNow:
    """Rule type: apply the consequence synchronously and return the verdict."""
    response = Response(
        user_id=user.id,
        session_id=session_id,
        sense_id=bound.sense_id,
        question_id=question_id,
        requested_level=bound.requested_level,
        served_level=bound.served_level,
        # No raw answer is kept for a rule grade: there is nothing left to grade it
        # with, and it is the learner's own text.
        raw_answer=None,
        idempotency_key=f"{session_id}:{question_id}",
    )
    session.add(response)
    await session.flush()
    outcome = await service.apply_checkpoint_result(
        session,
        redis,
        response=response,
        verdict=bool(evaluation.correct),
        score=evaluation.score,
        feedback=evaluation.feedback,
        now=now,
        render_format=bound.render_format,
        reveal=evaluation.reveal,
    )
    return GradedNow(
        response_id=outcome.response_id,
        sense_id=bound.sense_id,
        render_format=bound.render_format,
        is_correct=outcome.is_correct,
        grade_score=outcome.grade_score,
        grade_feedback=outcome.grade_feedback,
        reveal=outcome.reveal,
        mastery_before=outcome.mastery_before,
        mastery_after=outcome.mastery_after,
    )


async def _defer(
    session: AsyncSession,
    redis: Redis,
    *,
    user: CurrentUser,
    session_id: str,
    question_id: int,
    bound: _Bound,
    answer: str,
    claim: _ClaimState,
) -> Deferred:
    """LLM type: charge the quota, persist the answer, hand off to the worker.

    Mutates ``claim`` at each point the durable state changes, so the caller's
    compensation cannot drift from what actually happened here — including when this
    function raises.
    """
    if not await session_store.take_grading_slot(redis, user.id):
        # Re-arm the very same question, because this rejection is the one case where
        # what is on screen is still exactly the question to answer. The budget is a
        # short rolling window and nothing durable was written, so the honest recovery
        # is "submit that same answer again in a moment".
        #
        # Re-armed rather than merely left alone: the consume-once CAS has already
        # cleared ``current_qid``, so doing nothing would fail the next
        # ``consume_delivered`` and return ``question_not_issued_for_session`` — a
        # session-desync code, shown to someone who had merely hit a rate limit, and
        # one the client recovers from by polling ``/next`` and discarding their typed
        # answer.
        #
        # And not ``restore_delivered`` either: that reopens the whole delivery
        # (clearing the claim, rewinding ``last_round_used``, un-excluding the id) so
        # the sense comes back as some *other* question later. Correct for a genuinely
        # aborted answer, wrong here, where the learner is still looking at this one.
        await session_store.set_delivered(redis, session_id, bound.sense_id, question_id)
        claim.value = _Claim.BIND_HELD
        raise ConflictError("answer_grading_quota_exceeded")

    # The slot is charged before this write, because the write is what commits the
    # learner to an LLM call. If the write itself fails, the charge has to be undone:
    # otherwise the learner paid for a grade that never happened and cannot retry
    # until the 5-minute window rolls. Only this one statement is guarded — once the
    # pending row is durable the slot is legitimately spent, and
    # `reconcile_pending_grades` owns the settle from there.
    try:
        response = await service.create_pending_response(
            session,
            user_id=user.id,
            session_id=session_id,
            sense_id=bound.sense_id,
            question_id=question_id,
            raw_answer=answer,
            idempotency_key=f"{session_id}:{question_id}",
            requested_level=bound.requested_level,
            served_level=bound.served_level,
            render_format=bound.render_format,
        )
    except Exception:
        await session_store.release_grading_slot(redis, user.id)
        raise

    # The pending row is durable (reconcile owns its settle); from here a failure must
    # not re-arm the consume-once bind. Set BEFORE the next await, so an exception
    # raised by any of them still sees the row as committed.
    claim.value = _Claim.COMMITTED
    await session_store.set_awaiting_grade(redis, session_id, bound.sense_id, True)
    dispatch = GradingDispatch(owner_id=str(user.id), response_id=str(response.id))
    submission = await task_service.submit_or_join(
        session,
        kind=TASK_KIND_GRADING,
        server_work_key=grading_work_key(str(response.id)),
        requester_id=user.id,
        command_kind="grading.submit",
        command_id=str(response.id),
        provenance="response-owner",
        dispatch=dispatch,
    )
    if submission.task_created:
        try:
            pool = await get_arq_pool()
            await pool.enqueue_job(
                JOB_NAME_FOR_KIND[TASK_KIND_GRADING],
                str(submission.task.id),
                *dispatch.job_args(),
            )
        except Exception:  # durable worker reconciliation retries the enqueue
            pass
    return Deferred(
        response_id=response.id,
        sense_id=bound.sense_id,
        render_format=bound.render_format,
        task_id=submission.task.id,
    )
