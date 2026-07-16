"""Learning routes: session start, next question, answer submission.

/answers takes ONLY a question_id + answer — never a client question payload. The
server re-fetches the authoritative question and grades that (answer-key tamper
protection). All session routes gate the deck via require_node_access.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import ConflictError, NotFoundError
from pycil.content.deps import get_lexi_client
from pycil.content.lexi_port import LexiClient
from pycil.db.redis import get_arq_pool, get_redis
from pycil.db.session import get_session
from pycil.hierarchy.access import require_node_access
from pycil.hierarchy.models import DeckAttributes, NodeType
from pycil.learning import question_delivery, service, session_queue, session_store
from pycil.learning.models import Response
from pycil.learning.router_question import choose_format
from pycil.learning.schemas import (
    AnswerRequest,
    GradeResponse,
    NextQuestionExhausted,
    NextQuestionPending,
    NextQuestionReady,
    SessionRead,
    SessionStart,
)

router = APIRouter(tags=["learning"])

def _seen_key(session_id: str) -> str:
    return f"session:seen:{session_id}"


@router.get("/responses/{response_id}", response_model=GradeResponse)
async def get_response(
    response_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> GradeResponse:
    response = await session.get(Response, response_id)
    if response is None or response.user_id != user.id:
        raise NotFoundError("response_not_found")
    return GradeResponse(
        response_id=response.id,
        grade_status=response.grade_status.value,
        sense_id=response.sense_id,
        is_correct=response.is_correct,
        grade_score=response.grade_score,
        grade_feedback=response.grade_feedback,
        mastery_before=response.mastery_before,
        mastery_after=response.mastery_after,
    )


@router.post("/sessions", response_model=SessionRead)
async def start_session(
    body: SessionStart,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> SessionRead:
    now = datetime.now(UTC)
    # A structural mutation can change the canonical resolver while this request
    # runs.  Retry once so the persisted queue always carries the generation it
    # was resolved from rather than labelling an old queue with a new generation.
    for _ in range(2):
        node = await require_node_access(session, body.node_id, user, write=False)
        generation = node.structural_generation
        queue_kwargs = {}
        if node.type == NodeType.DECK:
            attributes = await session.get(DeckAttributes, node.id)
            new_per_batch, review_per_batch = session_queue.ratio_from_settings(
                attributes.settings if attributes else None
            )
            queue_kwargs = {
                "new_per_batch": new_per_batch,
                "review_per_batch": review_per_batch,
            }
        queue = await session_queue.build_queue(
            session, user.id, body.node_id, now, **queue_kwargs
        )
        node = await require_node_access(session, body.node_id, user, write=False)
        if node.structural_generation == generation:
            break
    else:
        raise ConflictError("session_scope_changed")
    session_id = uuid.uuid4().hex
    redis = get_redis()
    state = await session_store.create(
        redis,
        session_id,
        owner_id=user.id,
        node_id=body.node_id,
        scope_generation=node.structural_generation,
        queue=[session_store.QueuedSense(item.sense_id, item.mastery) for item in queue],
    )
    return SessionRead(
        session_id=session_id,
        node_id=body.node_id,
        queue_size=len(queue),
        expires_at=state.expires_at.isoformat(),
        first_state="pending" if queue else "exhausted",
    )


@router.get(
    "/sessions/{session_id}/next",
    response_model=NextQuestionReady | NextQuestionPending | NextQuestionExhausted,
)
async def next_question(
    session_id: str,
    user: Annotated[CurrentUser, Depends(current_user)],
    client: LexiClient = Depends(get_lexi_client),
    session: AsyncSession = Depends(get_session),
):
    redis = get_redis()
    state = await session_store.get(redis, session_id)
    if state is None or state.owner_id != user.id:
        raise NotFoundError("session_not_found")
    node = await require_node_access(session, state.node_id, user, write=False)
    if node.structural_generation != state.scope_generation:
        raise ConflictError("session_scope_changed")
    if state.issue and state.issue["state"] == "ready":
        return NextQuestionReady(**state.issue)
    if state.issue and state.issue["state"] == "answering":
        return NextQuestionPending(
            sense_id=state.issue["sense_id"],
            recommended_type=state.issue["recommended_type"],
        )
    if state.cursor >= len(state.queue):
        return NextQuestionExhausted()

    item = state.queue[state.cursor]
    recommended_type = choose_format(item.mastery, f"{item.sense_id}:{session_id}")
    issue_was_new = not state.issue
    pending_issue = state.issue if state.issue else None
    lease_expired = (
        pending_issue is not None
        and pending_issue.get("state") == "generation_pending"
        and pending_issue.get("lease_until", "") <= datetime.now(UTC).isoformat()
    )
    if issue_was_new:
        reserved = await session_store.reserve_issue(
            redis,
            session_id,
            {
                "state": "generation_pending",
                "sense_id": item.sense_id,
                "recommended_type": recommended_type,
            },
        )
        state = await session_store.get(redis, session_id)
        if state is None:
            raise NotFoundError("session_not_found")
        if state.issue and state.issue["state"] == "ready":
            return NextQuestionReady(**state.issue)
        if not reserved:
            if state.issue:
                return NextQuestionPending(
                    sense_id=state.issue["sense_id"],
                    recommended_type=state.issue["recommended_type"],
                )
            raise NotFoundError("session_not_found")

    question = await question_delivery.find_question(
        client, item.sense_id, recommended_type
    )
    if question is None:
        if issue_was_new or lease_expired:
            word_lookup = getattr(client, "word_id_for_sense", None)
            word_id = await word_lookup(item.sense_id) if word_lookup else None
            if word_id is not None:
                if not await session_store.take_generation_slot(redis, user.id):
                    raise ConflictError("question_generation_quota_exceeded")
                pool = await get_arq_pool()
                try:
                    job = await pool.enqueue_job(
                        "generate_question",
                        str(user.id),
                        word_id,
                        [recommended_type],
                        1,
                        session_id,
                        item.sense_id,
                    )
                except Exception:
                    if issue_was_new:
                        await session_store.clear_issue(redis, session_id)
                    raise
                if not await session_store.replace_issue(
                    redis,
                    session_id,
                    {
                        "state": "generation_pending",
                        "sense_id": item.sense_id,
                        "recommended_type": recommended_type,
                        "job_id": job.job_id,
                        "lease_until": (
                            datetime.now(UTC) + timedelta(seconds=60)
                        ).replace(microsecond=0).isoformat(),
                    },
                ):
                    raise NotFoundError("session_not_found")
        return NextQuestionPending(sense_id=item.sense_id, recommended_type=recommended_type)
    if question.sense_id != item.sense_id or question.format != recommended_type:
        raise ConflictError("question_delivery_mismatch")
    issue = {"state": "ready", **question_delivery.ready_payload(question, recommended_type)}
    if not await session_store.replace_issue(redis, session_id, issue):
        raise NotFoundError("session_not_found")
    return NextQuestionReady(**issue)


@router.post("/answers", response_model=GradeResponse)
async def submit_answer(
    body: AnswerRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiClient = Depends(get_lexi_client),
) -> GradeResponse:
    redis = get_redis()
    state = await session_store.get(redis, body.session_id)
    if state is None or state.owner_id != user.id:
        raise NotFoundError("session_not_found")
    node = await require_node_access(session, state.node_id, user, write=False)
    if node.structural_generation != state.scope_generation:
        raise ConflictError("session_scope_changed")
    issue = state.issue
    if (
        not issue
        or issue.get("state") != "ready"
        or issue.get("question_id") != body.question_id
    ):
        raise ConflictError("question_not_issued_for_session")
    question = await client.get_question(body.question_id)
    if question is None or question.sense_id != issue["sense_id"]:
        raise ConflictError("question_not_issued_for_session")
    claimed_issue = await session_store.claim_issue(
        redis, body.session_id, body.question_id
    )
    if claimed_issue is None:
        raise ConflictError("question_not_issued_for_session")

    try:
        if question.format == "use_in_sentence":
            if not await session_store.take_grading_slot(redis, user.id):
                raise ConflictError("answer_grading_quota_exceeded")
            response = await service.create_pending_response(
                session,
                user_id=user.id,
                session_id=body.session_id,
                sense_id=question.sense_id,
                question_id=body.question_id,
                raw_answer=body.answer,
                idempotency_key=f"{body.session_id}:{body.question_id}",
            )
            pool = await get_arq_pool()
            await pool.enqueue_job("grade_answer_v1", str(user.id), str(response.id))
            await session_store.complete_issue(redis, body.session_id, body.question_id)
            return GradeResponse(
                response_id=response.id,
                grade_status="pending",
                sense_id=question.sense_id,
            )
        outcome = await service.answer(
            session=session,
            client=client,
            user_id=user.id,
            question_id=body.question_id,
            raw_answer=body.answer,
            session_id=body.session_id,
            now=datetime.now(UTC),
            seen_senses=set(),
        )
    except Exception:
        await session_store.restore_ready_issue(redis, body.session_id, claimed_issue)
        raise
    await session_store.complete_issue(redis, body.session_id, body.question_id)
    # Publish the grading verdict to the owner-scoped channel (best-effort; the
    # verdict is already persisted to responses, recoverable on a missed push).
    from shared.realtime import channels
    from shared.realtime.payloads import GradingResult

    from pycil.realtime import client as centrifugo

    await centrifugo.publish(
        channels.user_grading(user.id, str(outcome.response_id)),
        GradingResult(
            response_id=str(outcome.response_id),
            sense_id=outcome.sense_id,
            is_correct=outcome.is_correct,
            grade_score=outcome.grade_score,
            grade_feedback=outcome.grade_feedback,
            mastery_before=outcome.mastery_before,
            mastery_after=outcome.mastery_after,
        ).to_dict(),
    )

    return GradeResponse(
        response_id=outcome.response_id,
        grade_status="graded",
        sense_id=outcome.sense_id,
        is_correct=outcome.is_correct,
        grade_score=outcome.grade_score,
        grade_feedback=outcome.grade_feedback,
        mastery_before=outcome.mastery_before,
        mastery_after=outcome.mastery_after,
    )
