"""One FSRS update per (session, sense) under concurrent apply (invariant #13).

Two concurrent submissions of a disqualifying answer for the same (session, sense)
must produce exactly one ``user_sense_stats`` mutation + one ``review_log`` row,
guaranteed by the Postgres first-attempt claim + advisory xact lock (Redis is
advisory only).
"""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.auth.models import User
from pycil.db.redis import get_redis
from pycil.learning import service, session_store
from pycil.learning.models import Response, ReviewLog
from pycil.learning.session_store import AdmittedSense

pytestmark = pytest.mark.asyncio


async def _apply_one(factory, redis, user_id, sid, sense_id, qid):
    async with factory() as session:
        response = Response(
            user_id=user_id, session_id=sid, sense_id=sense_id, question_id=qid,
            requested_level=2, served_level=2, raw_answer=None,
            idempotency_key=f"{sid}:{qid}",
        )
        session.add(response)
        await session.flush()
        return await service.apply_checkpoint_result(
            session, redis, response=response, verdict=False, score=0.0,
            feedback=None, now=datetime.now(UTC),
        )


async def test_concurrent_disqualifier_applies_one_fsrs(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    redis = get_redis()

    async with factory() as session:
        user = User(email=f"conc-{uuid.uuid4().hex[:8]}@x.co")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    sid = uuid.uuid4().hex
    await session_store.create(
        redis, sid, owner_id=user.id, node_id=uuid.uuid4(), scope_generation=1,
        target_words=1, max_per_round=4, admitted=[AdmittedSense(70, "due", [2, 2])],
    )

    # Two concurrent submissions (distinct question ids, same session/sense).
    outcomes = await asyncio.gather(
        _apply_one(factory, redis, user.id, sid, 70, 900),
        _apply_one(factory, redis, user.id, sid, 70, 901),
    )
    applied = [o for o in outcomes if o.fsrs_applied]
    assert len(applied) == 1  # exactly one submission won the claim

    async with factory() as session:
        logs = (
            await session.execute(select(ReviewLog).where(ReviewLog.user_id == user.id))
        ).scalars().all()
    assert len(logs) == 1 and logs[0].grade == 1
