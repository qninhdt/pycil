"""Recoverable stream, failure sanitization, retention, and race contracts."""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from pycil.assistant import router
from pycil.assistant.application import run_service
from pycil.assistant.application.hitl import claim_decision, create_pending_action
from pycil.assistant.domain.context import AssistantContext
from pycil.assistant.infra.models import AssistantActionAudit, AssistantRunEvent, RunStatus
from pycil.common.errors import ConflictError

from .conftest import create_run, create_thread, create_user

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "worker"))
from pycil_worker.jobs import reconcile_assistant_retention as retention_job  # noqa: E402

pytestmark = pytest.mark.asyncio


async def test_streaming_routes_publish_a_named_sse_openapi_contract():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router.router, prefix="/v1")
    operation = app.openapi()["paths"]["/v1/assistant/threads/{thread_id}/messages"]["post"]
    response = operation["responses"]["200"]
    assert "text/event-stream" in response["content"]
    assert operation["x-pycil-sse-contract"]["eventSchema"] == (
        "#/components/schemas/AssistantSSEEvent"
    )


def _session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def test_persisted_events_are_ordered_and_recoverable_after_last_event_id(
    engine, session, monkeypatch
):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    run = await create_run(session, thread.id, owner.id, uuid4())
    factory = _session_factory(engine)
    monkeypatch.setattr(run_service, "async_session_factory", factory)
    monkeypatch.setattr(router, "async_session_factory", factory)

    first = await run_service.append_event(run.id, "token", {"content": "one"})
    second = await run_service.append_event(run.id, "token", {"content": "two"})
    final = await run_service.append_event(run.id, "done", {})

    assert [first.sequence, second.sequence, final.sequence] == [1, 2, 3]
    recovered = [frame async for frame in router._persisted_events(run.id, after=1)]
    assert recovered == [
        'id: 2\nevent: token\ndata: {"content":"two"}\n\n',
        "id: 3\nevent: done\ndata: {}\n\n",
    ]


async def test_run_deadline_persists_only_sanitized_error_and_releases_lease(
    engine, session, monkeypatch
):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    run = await create_run(session, thread.id, owner.id, uuid4())
    factory = _session_factory(engine)
    monkeypatch.setattr(run_service, "async_session_factory", factory)
    monkeypatch.setattr(run_service.settings, "assistant_run_deadline_seconds", 1)

    class NeverReturnsGraph:
        async def astream(self, *args, **kwargs):
            del args, kwargs
            await asyncio.sleep(1)
            yield None

    events = [
        event
        async for event in run_service.stream_run(
            NeverReturnsGraph(),
            run,
            AssistantContext(owner.id, owner.token_version),
            content="hello",
        )
    ]
    assert [(event.event_type, event.sanitized_payload) for event in events] == [
        ("error", {"code": "deadline_exceeded"})
    ]
    async with factory() as verify:
        persisted_run = await verify.get(type(run), run.id)
        persisted_events = list(
            await verify.scalars(
                select(AssistantRunEvent).where(AssistantRunEvent.run_id == run.id)
            )
        )
    assert persisted_run.status == RunStatus.FAILED
    assert persisted_run.error_code == "deadline_exceeded"
    assert [event.sanitized_payload for event in persisted_events] == [
        {"code": "deadline_exceeded"}
    ]
    assert await run_service.get_redis().get(f"assistant:run:{owner.id}:{thread.id}") is None


async def test_redis_lease_fails_closed_for_rate_and_monthly_spend(monkeypatch):
    owner_id, thread_id, run_id = uuid4(), uuid4(), uuid4()
    monkeypatch.setattr(run_service.settings, "assistant_per_user_concurrency", 9)
    monkeypatch.setattr(run_service.settings, "assistant_global_concurrency", 9)
    monkeypatch.setattr(run_service.settings, "assistant_requests_per_minute", 1)
    monkeypatch.setattr(run_service.settings, "assistant_monthly_budget_usd", 0.0)
    assert await run_service.acquire_lease(owner_id, thread_id, run_id)
    assert not await run_service.acquire_lease(owner_id, uuid4(), uuid4())
    await run_service.release_lease(owner_id, thread_id, run_id)

    monkeypatch.setattr(run_service.settings, "assistant_requests_per_minute", 9)
    monkeypatch.setattr(run_service.settings, "assistant_monthly_budget_usd", 0.000001)
    assert not await run_service.acquire_lease(owner_id, uuid4(), uuid4())


async def test_simultaneous_action_decisions_have_one_atomic_winner(engine, session):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    run = await create_run(session, thread.id, owner.id, uuid4())
    action = await create_pending_action(
        session,
        run_id=run.id,
        owner_id=owner.id,
        tool="delete_node",
        arguments={},
        checkpoint_version=f"run:{run.id}",
    )
    factory = _session_factory(engine)

    async def decide(decision: str):
        async with factory() as contender:
            return await claim_decision(contender, action.id, owner.id, decision)

    results = await asyncio.gather(decide("approve"), decide("reject"), return_exceptions=True)
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, ConflictError) for result in results) == 1


async def test_retention_deletes_private_records_but_preserves_then_expires_audits(
    engine, session, monkeypatch
):
    owner = await create_user(session)
    expired_thread = await create_thread(session, owner.id)
    expired_thread.retention_deadline = datetime.now(UTC) - timedelta(seconds=1)
    run = await create_run(session, expired_thread.id, owner.id, uuid4())
    action = await create_pending_action(
        session,
        run_id=run.id,
        owner_id=owner.id,
        tool="publish_node",
        arguments={},
        checkpoint_version=f"run:{run.id}",
    )
    old_audit = AssistantActionAudit(
        action_id=None,
        actor_id=owner.id,
        decision="historic",
        sanitized_digest="f" * 64,
        correlation_id=uuid4(),
        occurred_at=datetime.now(UTC) - timedelta(days=91),
    )
    session.add(old_audit)
    await session.commit()
    factory = _session_factory(engine)

    class Cursor:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, *args):
            del args

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def cursor(self):
            return Cursor()

    async def connect(*args, **kwargs):
        del args, kwargs
        return Connection()

    monkeypatch.setattr(retention_job, "AsyncConnection", SimpleNamespace(connect=connect))
    assert await retention_job.reconcile_assistant_retention({"session_factory": factory}) == 1

    async with factory() as verify:
        assert await verify.get(type(expired_thread), expired_thread.id) is None
        preserved = list(
            await verify.scalars(
                select(AssistantActionAudit).where(
                    AssistantActionAudit.correlation_id == action.correlation_id
                )
            )
        )
        assert await verify.get(AssistantActionAudit, old_audit.id) is None
    assert preserved
    assert all(entry.action_id is None for entry in preserved)
