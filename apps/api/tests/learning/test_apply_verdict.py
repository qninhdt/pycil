"""apply_verdict: worker settle of a PENDING (llm) grade — idempotent, no re-bill."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from lexi_ai.contracts import Evaluation
from sqlalchemy import select

from pycil.auth.models import User
from pycil.db.redis import get_redis
from pycil.hierarchy import service as hierarchy_service
from pycil.hierarchy.models import NodeType
from pycil.learning import service, session_store
from pycil.learning.models import GradeStatus, Response, ReviewLog
from pycil.learning.session_store import AdmittedSense

pytestmark = pytest.mark.asyncio


class CountingGrader:
    """Judge-backed engine that counts evaluate_answer calls (proves no re-bill)."""

    def __init__(self, correct: bool = True):
        self._correct = correct
        self.calls = 0

    async def evaluate_answer(self, question_id, answer):
        self.calls += 1
        return Evaluation(
            question_id=str(question_id),
            status="graded",
            correct=self._correct,
            score=1.0 if self._correct else 0.0,
            feedback="judged",
        )


async def _user(session) -> User:
    user = User(email=f"settle-{uuid.uuid4().hex[:8]}@x.co")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _deck(session, owner_id):
    """A real deck row.

    `ReviewLog.node_id` is a foreign key to `nodes.id` (SET NULL on delete), so a
    session created with a fabricated `node_id` now fails the insert instead of
    silently writing NULL. Tests that drive `apply_checkpoint_result` therefore need
    a node that exists.
    """
    node = await hierarchy_service.create_node(
        session, owner_id, node_type=NodeType.DECK, name=f"deck-{uuid.uuid4().hex[:6]}"
    )
    return node.id


async def _pending(session, redis, user, sense_id=42, qid=1):
    sid = uuid.uuid4().hex
    await session_store.create(
        redis, sid, owner_id=user.id, node_id=await _deck(session, user.id),
        scope_generation=1, target_words=1, max_per_round=4,
        admitted=[AdmittedSense(sense_id, "due", [3, 3])],
    )
    # Advance to the final checkpoint so a correct settle completes N -> Good.
    await session_store.pass_checkpoint(redis, sid, sense_id, required_checkpoints=2)
    resp = Response(
        user_id=user.id, session_id=sid, sense_id=sense_id, question_id=qid,
        grade_status=GradeStatus.pending, raw_answer="a sentence",
        requested_level=3, served_level=3,
    )
    session.add(resp)
    await session.commit()
    await session.refresh(resp)
    return sid, resp


async def test_apply_verdict_settles_pending(session):
    redis = get_redis()
    user = await _user(session)
    _, resp = await _pending(session, redis, user)
    grader = CountingGrader(correct=True)

    out = await service.apply_verdict(session, redis, grader, resp.id, datetime.now(UTC))
    assert out is not None and out.is_correct
    assert grader.calls == 1
    await session.refresh(resp)
    assert resp.grade_status == GradeStatus.graded
    logs = (await session.execute(select(ReviewLog))).scalars().all()
    assert len(logs) == 1


async def test_apply_verdict_retry_is_noop(session):
    redis = get_redis()
    user = await _user(session)
    _, resp = await _pending(session, redis, user)
    grader = CountingGrader(correct=True)

    first = await service.apply_verdict(session, redis, grader, resp.id, datetime.now(UTC))
    assert first is not None and grader.calls == 1
    second = await service.apply_verdict(session, redis, grader, resp.id, datetime.now(UTC))
    assert second is None and grader.calls == 1  # terminal -> not re-billed
    logs = (await session.execute(select(ReviewLog))).scalars().all()
    assert len(logs) == 1


async def test_apply_verdict_skips_another_workers_active_lease(session):
    redis = get_redis()
    user = await _user(session)
    _, resp = await _pending(session, redis, user)
    resp.grading_lease_owner = "other-worker"
    resp.grading_lease_expires_at = datetime.now(UTC) + timedelta(minutes=1)
    await session.commit()
    grader = CountingGrader(correct=True)
    assert await service.apply_verdict(session, redis, grader, resp.id, datetime.now(UTC)) is None
    assert grader.calls == 0


async def test_still_pending_evaluation_left_for_reconcile(session):
    redis = get_redis()
    user = await _user(session)
    _, resp = await _pending(session, redis, user)

    class StillPendingGrader:
        async def evaluate_answer(self, question_id, answer):
            return Evaluation(question_id=str(question_id), status="pending")

    grader = StillPendingGrader()
    out = await service.apply_verdict(session, redis, grader, resp.id, datetime.now(UTC))
    assert out is None
    await session.refresh(resp)
    assert resp.grade_status == GradeStatus.pending  # left pending for reconcile


async def test_pending_response_reuses_idempotency_key(session):
    user = await _user(session)
    kwargs = {
        "user_id": user.id, "session_id": "session-1", "sense_id": 42,
        "question_id": 1, "raw_answer": "my sentence", "idempotency_key": "session-1:1",
        "requested_level": 3, "served_level": 3, "render_format": "free_text",
    }
    first = await service.create_pending_response(session, **kwargs)
    retry = await service.create_pending_response(session, **kwargs)
    assert retry.id == first.id
    responses = (await session.execute(select(Response))).scalars().all()
    assert len(responses) == 1
