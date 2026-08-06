"""The pending-grade reconciler: expiry, the lease it must respect, and the ceiling.

This job had no tests. It is the only thing that discards a learner's answer text,
so the two conditions that decide *when* it does so are worth pinning precisely:

* it must not destroy `raw_answer` while a worker holds a live grading lease, and
* it must still terminate a row whose lease is renewed forever by a crash loop.

Those pull in opposite directions, which is why both are asserted here. Fixing only
the first introduces the starvation the second catches.
"""

import os
from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from pycil.auth.models import User
from pycil.db.models import target_metadata
from pycil.learning.infra.models import GradeStatus, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pycil_worker.jobs.reconcile_pending_grades import (
    EXPIRY_HOURS,
    HARD_CEILING_HOURS,
    reconcile_pending_grades,
)


@pytest.fixture(scope="session")
def reconcile_db_url() -> Iterator[str]:
    """A PostgreSQL to run against.

    The worker package does not depend on `testcontainers` the way `apps/api` does,
    so this needs a database supplied from outside. Skipped rather than failed when
    none is configured: the assertions here are about SQL predicates and cannot be
    faked against an in-memory double.
    """
    configured = os.environ.get("TEST_DB_URL") or os.environ.get("WORKER_TEST_DB_URL")
    if not configured:
        pytest.skip("set TEST_DB_URL to an asyncpg DSN to run the reconciler tests")
    yield configured


@pytest_asyncio.fixture
async def factory(reconcile_db_url: str) -> AsyncGenerator[async_sessionmaker, None]:
    engine = create_async_engine(reconcile_db_url, poolclass=None)
    async with engine.begin() as conn:
        await conn.run_sync(target_metadata.drop_all)
        await conn.run_sync(target_metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(target_metadata.drop_all)
    await engine.dispose()


class _Redis:
    def __init__(self) -> None:
        self.jobs: list[tuple] = []

    async def enqueue_job(self, *args):
        self.jobs.append(args)


async def _learner(factory) -> User:
    async with factory() as session:
        user = User(email=f"reconcile-{uuid4().hex[:8]}@x.co")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _pending(
    factory,
    user: User,
    *,
    age_hours: float,
    lease_expires_in: timedelta | None = None,
) -> Response:
    """A pending row answered `age_hours` ago, optionally under a live lease."""
    now = datetime.now(UTC)
    async with factory() as session:
        response = Response(
            user_id=user.id,
            session_id=uuid4().hex,
            sense_id=1,
            question_id=1,
            raw_answer="the learner's sentence",
            grade_status=GradeStatus.pending,
            answered_at=now - timedelta(hours=age_hours),
            idempotency_key=uuid4().hex,
        )
        if lease_expires_in is not None:
            response.grading_lease_owner = uuid4().hex
            response.grading_lease_expires_at = now + lease_expires_in
        session.add(response)
        await session.commit()
        await session.refresh(response)
        return response


async def _reload(factory, response_id) -> Response:
    async with factory() as session:
        return await session.get(Response, response_id)


async def _run(factory) -> dict:
    return await reconcile_pending_grades(
        {"session_factory": factory, "redis": _Redis()}
    )


async def test_a_live_lease_protects_the_answer_text(factory):
    """B4. The purge must not null `raw_answer` out from under an active grade.

    The row is old enough to expire, but a worker is mid-LLM-call on it. Destroying
    the text here loses a verdict the learner has already paid for, and leaves
    `apply_verdict` with nothing to apply — it used to raise
    `response_raw_answer_missing`, which no retry could ever recover from.
    """
    user = await _learner(factory)
    leased = await _pending(
        factory, user, age_hours=EXPIRY_HOURS + 1, lease_expires_in=timedelta(minutes=4)
    )

    result = await _run(factory)

    row = await _reload(factory, leased.id)
    assert row.grade_status == GradeStatus.pending, "a leased row must not be expired"
    assert row.raw_answer is not None, "the answer text must survive the sweep"
    assert result["purged"] == 0


async def test_an_expired_lease_no_longer_protects_it(factory):
    """The lease is a grace period, not immunity: once it lapses the purge applies."""
    user = await _learner(factory)
    stale = await _pending(
        factory,
        user,
        age_hours=EXPIRY_HOURS + 1,
        lease_expires_in=timedelta(minutes=-1),
    )

    result = await _run(factory)

    row = await _reload(factory, stale.id)
    assert row.grade_status == GradeStatus.expired
    assert row.raw_answer is None
    assert result["purged"] == 1


async def test_a_crash_looping_lease_still_terminates_at_the_ceiling(factory):
    """The starvation the lease condition would otherwise introduce.

    A worker that dies mid-LLM-call never advances `answered_at`, so this sweep
    re-leases the row on every pass. With a lease-aware purge and nothing else, the
    row would be immortal and each pass would spend another LLM call on it. The
    ceiling ignores the lease for exactly this case.

    The lease here is renewed into the future on every run, which is what a crash
    loop looks like from the database's side.
    """
    user = await _learner(factory)
    immortal = await _pending(
        factory,
        user,
        age_hours=HARD_CEILING_HOURS + 1,
        lease_expires_in=timedelta(minutes=5),
    )

    result = await _run(factory)

    row = await _reload(factory, immortal.id)
    assert row.grade_status == GradeStatus.expired, (
        "a continuously re-leased row must still terminate at the hard ceiling"
    )
    assert row.raw_answer is None
    assert result["starved"] == 1
    assert row.grading_lease_owner is None, "the dead lease must be cleared"


async def test_a_fresh_answer_is_left_alone(factory):
    user = await _learner(factory)
    fresh = await _pending(factory, user, age_hours=1)

    result = await _run(factory)

    row = await _reload(factory, fresh.id)
    assert row.grade_status == GradeStatus.pending
    assert row.raw_answer is not None
    assert result["purged"] == 0
    assert result["starved"] == 0


async def test_an_unleased_pending_row_is_requeued(factory):
    """The requeue path still works, and reports what it enqueued."""
    user = await _learner(factory)
    orphan = await _pending(factory, user, age_hours=1)

    redis = _Redis()
    result = await reconcile_pending_grades(
        {"session_factory": factory, "redis": redis}
    )

    assert result["requeued"] == 1
    assert redis.jobs == [("grade_answer_v1", str(user.id), str(orphan.id))]


async def test_a_leased_row_is_not_requeued(factory):
    """Two workers must not grade the same answer concurrently."""
    user = await _learner(factory)
    await _pending(factory, user, age_hours=1, lease_expires_in=timedelta(minutes=4))

    redis = _Redis()
    result = await reconcile_pending_grades(
        {"session_factory": factory, "redis": redis}
    )

    assert result["requeued"] == 0
    assert redis.jobs == []
