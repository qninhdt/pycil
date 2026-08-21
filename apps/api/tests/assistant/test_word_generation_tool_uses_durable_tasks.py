"""The assistant tool and the HTTP route share one word-generation pipeline.

A second pipeline backed by its own table meant the two producers wrote different
rows, sent different notifications and retried differently for one feature, while
both charged the same quota. These tests pin the properties that made the split
observable, so a future edit that reintroduces a separate path fails here.

The tools are ``StructuredTool`` instances, so the underlying coroutine is invoked
directly: building a real ``ToolRuntime`` would require seven unrelated fields
that none of this behaviour reads.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from pycil.assistant.application import tools
from pycil.auth.models import User
from pycil.common.errors import AppError, TooManyRequestsError
from pycil.content.application import generation_quota
from pycil.tasks.application import dispatch as task_dispatch
from pycil.tasks.domain.vocabulary import JOB_NAME_FOR_KIND, TASK_KIND_WORD, WordDispatch
from pycil.tasks.infra.models import AsyncTask

pytestmark = pytest.mark.asyncio

_generate = tools.request_word_generation.coroutine


async def _seed_user(session) -> User:
    user = User(email=f"assistant-{uuid4().hex[:8]}@example.test")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _runtime(user: User) -> SimpleNamespace:
    return SimpleNamespace(
        context=SimpleNamespace(user_id=user.id, token_version=0, action_id=None)
    )


@pytest.fixture
def enqueued(monkeypatch) -> list[tuple]:
    """Capture arq enqueues without a Redis queue.

    The enqueue lives in the shared dispatch helper now, so that is the seam to
    replace — no producer imports the pool itself any more.
    """
    calls: list[tuple] = []

    class Pool:
        async def enqueue_job(self, *args):
            calls.append(args)

    async def get_pool():
        return Pool()

    monkeypatch.setattr(task_dispatch, "get_arq_pool", get_pool)
    return calls


@pytest.fixture
def bind_session(monkeypatch, engine):
    """Point the tool's own session factory at the test database."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def scope():
        async with factory() as scoped:
            yield scoped

    monkeypatch.setattr(tools, "async_session_factory", scope)
    return factory


async def test_the_tool_creates_a_durable_task_and_enqueues_the_shared_job(
    session, enqueued, bind_session
):
    user = await _seed_user(session)

    result = await _generate("serendipity", _runtime(user))

    task = (await session.execute(select(AsyncTask))).scalars().one()
    assert task.kind == TASK_KIND_WORD
    assert result == f"generation_requested:{task.id}"
    # The dispatch payload is what the reconciler re-enqueues from, so a task the
    # arq enqueue never reached is still recoverable.
    assert task.dispatch == WordDispatch(query="serendipity", owner_id=str(user.id)).to_dispatch()
    assert enqueued == [
        (
            JOB_NAME_FOR_KIND[TASK_KIND_WORD],
            str(task.id),
            "serendipity",
            str(user.id),
        )
    ]


async def test_both_producers_join_one_task_for_the_same_word(
    session, client, enqueued, bind_session
):
    """The work key, not the producer, decides identity.

    This is the property the two-pipeline split could not have: the tool and the
    route now converge on one row for one word.
    """
    from pycil.auth.deps import current_user
    from pycil.auth.schemas import CurrentUser

    user = await _seed_user(session)
    await _generate("ephemeral", _runtime(user))

    client._transport.app.dependency_overrides[current_user] = lambda: CurrentUser(
        id=user.id, email=user.email
    )
    response = await client.post("/v1/word-generations", json={"query": "ephemeral"})

    assert response.status_code == 202
    total = await session.scalar(select(func.count()).select_from(AsyncTask))
    assert total == 1
    assert response.json()["taskId"] == str(
        (await session.execute(select(AsyncTask))).scalars().one().id
    )


async def test_joining_an_existing_task_returns_the_reserved_quota_slot(
    session, fake_redis, enqueued, bind_session
):
    """A join reserved a slot it never spends.

    Without the release, repeatedly asking for a word already being generated
    exhausted the learner's inflight budget until the 900s TTL lapsed.
    """
    user = await _seed_user(session)
    await _generate("liminal", _runtime(user))
    inflight_key = f"word-generation:inflight:user:{user.id}"
    after_first = int(await fake_redis.get(inflight_key) or 0)

    await _generate("liminal", _runtime(user))

    assert int(await fake_redis.get(inflight_key) or 0) == after_first
    assert await session.scalar(select(func.count()).select_from(AsyncTask)) == 1


async def test_the_tool_refuses_once_the_shared_quota_is_exhausted(
    session, fake_redis, monkeypatch, bind_session
):
    user = await _seed_user(session)

    async def exhausted(*_args, **_kwargs):
        return False

    monkeypatch.setattr(generation_quota, "reserve_quota", exhausted)

    with pytest.raises(TooManyRequestsError, match="word_generation_quota_exceeded"):
        await _generate("serendipity", _runtime(user))

    assert await session.scalar(select(func.count()).select_from(AsyncTask)) == 0


@pytest.mark.parametrize("query", ["", "   ", "x" * 201])
async def test_the_tool_rejects_a_query_the_route_would_reject(session, query, bind_session):
    """The route validates at the boundary; silently slicing here would generate
    an entry for a word the caller did not ask for."""
    user = await _seed_user(session)

    with pytest.raises(AppError, match="word_generation_query_invalid"):
        await _generate(query, _runtime(user))

    assert await session.scalar(select(func.count()).select_from(AsyncTask)) == 0


async def test_a_failed_submission_does_not_keep_the_quota_slot(
    session, fake_redis, monkeypatch, bind_session
):
    user = await _seed_user(session)

    async def boom(*_args, **_kwargs):
        raise RuntimeError("submission failed")

    monkeypatch.setattr(task_dispatch.task_service, "submit_or_join", boom)

    with pytest.raises(RuntimeError, match="submission failed"):
        await _generate("serendipity", _runtime(user))

    assert int(await fake_redis.get(f"word-generation:inflight:user:{user.id}") or 0) == 0
