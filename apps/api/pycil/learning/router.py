"""Learning routes: session start, next question, answer submission.

/answers takes ONLY a question_id + answer — never a client question payload. The
server re-fetches the authoritative question and grades that (answer-key tamper
protection). All session routes gate the deck via require_node_access.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import NotFoundError
from pycil.content.deps import get_lexi_client
from pycil.content.lexi_port import LexiClient
from pycil.db.redis import get_redis
from pycil.db.session import get_session
from pycil.hierarchy.access import require_node_access
from pycil.learning import service, session_queue
from pycil.learning.schemas import (
    AnswerRequest,
    GradeResponse,
    SessionRead,
    SessionStart,
)

router = APIRouter(tags=["learning"])

_SESSION_TTL = 8 * 3600


def _seen_key(session_id: str) -> str:
    return f"session:seen:{session_id}"


@router.post("/sessions", response_model=SessionRead)
async def start_session(
    body: SessionStart,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> SessionRead:
    await require_node_access(session, body.node_id, user, write=False)
    now = datetime.now(UTC)
    queue = await session_queue.build_queue(session, user.id, body.node_id, now)
    session_id = uuid.uuid4().hex
    redis = get_redis()
    await redis.hset(
        f"session:{session_id}",
        mapping={"user": str(user.id), "node": str(body.node_id)},
    )
    await redis.expire(f"session:{session_id}", _SESSION_TTL)
    return SessionRead(session_id=session_id, node_id=body.node_id, queue_size=len(queue))


@router.post("/answers", response_model=GradeResponse)
async def submit_answer(
    body: AnswerRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiClient = Depends(get_lexi_client),
) -> GradeResponse:
    redis = get_redis()
    meta = await redis.hgetall(f"session:{body.session_id}")
    if not meta or meta.get("user") != str(user.id):
        raise NotFoundError("session_not_found")

    # First-attempt-per-sense marker set persisted in Redis per session.
    seen_raw = await redis.smembers(_seen_key(body.session_id))
    seen = {int(s) for s in seen_raw}

    outcome = await service.answer(
        session=session,
        client=client,
        user_id=user.id,
        question_id=body.question_id,
        raw_answer=body.answer,
        session_id=body.session_id,
        now=datetime.now(UTC),
        seen_senses=seen,
    )
    await redis.sadd(_seen_key(body.session_id), outcome.sense_id)
    await redis.expire(_seen_key(body.session_id), _SESSION_TTL)

    # Publish the grading verdict to the owner-scoped channel (best-effort; the
    # verdict is already persisted to responses, recoverable on a missed push).
    from shared.realtime import channels
    from shared.realtime.payloads import GradingResult

    from pycil.realtime import client as centrifugo

    await centrifugo.publish(
        channels.user_grading(user.id, str(body.question_id)),
        GradingResult(
            response_id=str(body.question_id),
            sense_id=outcome.sense_id,
            is_correct=outcome.is_correct,
            grade_score=outcome.grade_score,
            grade_feedback=outcome.grade_feedback,
        ).to_dict(),
    )

    return GradeResponse(
        sense_id=outcome.sense_id,
        is_correct=outcome.is_correct,
        grade_score=outcome.grade_score,
        grade_feedback=outcome.grade_feedback,
        mastery_before=outcome.mastery_before,
        mastery_after=outcome.mastery_after,
    )
