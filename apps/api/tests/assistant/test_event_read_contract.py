"""The two non-streaming event reads, exercised over HTTP.

These endpoints had a 500 on their first row for as long as they have existed, and
the existing suite did not catch it because it asserts on the OpenAPI *document*
rather than calling anything: `RunEventRead` declared `serialization_alias` only,
which names the output field and is not accepted on input, so the router's
`RunEventRead(eventType=...)` keyword failed validation every time.

So these tests call the routes. A schema assertion alone would have passed against
the broken version too.
"""

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.assistant.application import run_service
from pycil.auth.deps import current_user
from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.db.session import get_session
from pycil.main import create_app

from .conftest import create_run, create_thread

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def assistant_client(engine, monkeypatch):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        owner = User(email="assistant-reader@example.test")
        session.add(owner)
        await session.commit()
        await session.refresh(owner)

    # `append_event` opens its own session, so it needs the test engine too.
    monkeypatch.setattr(run_service, "async_session_factory", factory)

    async def override_session():
        async with factory() as session:
            yield session

    async def override_user() -> CurrentUser:
        return CurrentUser(id=owner.id, email=owner.email)

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[current_user] = override_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory, owner


async def test_thread_messages_serves_camel_case_events_rather_than_failing(
    assistant_client,
):
    client, factory, owner = assistant_client
    async with factory() as session:
        thread = await create_thread(session, owner.id)
        run = await create_run(session, thread.id, owner.id, uuid4())

    await run_service.append_event(run.id, "user_message", {"content": "hello"})
    await run_service.append_event(run.id, "token", {"content": "hi "})
    await run_service.append_event(run.id, "done", {})

    response = await client.get(f"/v1/assistant/threads/{thread.id}/messages")

    assert response.status_code == 200
    events = response.json()
    assert [event["eventType"] for event in events] == ["user_message", "token", "done"]
    # The token payload is an object, not a bare string. A client that concatenated
    # the payload itself would render "undefined" for every token.
    assert events[1]["payload"] == {"content": "hi "}


async def test_events_carry_their_run_so_a_thread_of_several_runs_stays_ordered(
    assistant_client,
):
    """`sequence` restarts at 1 per run, so it cannot identify an event on its own.

    A thread accumulates one run per turn, and this endpoint returns all of them.
    Without `runId` a client keying events by sequence would collapse turn two's
    first event onto turn one's, silently losing most of the transcript — and would
    have no way to name a run for recovery.
    """
    client, factory, owner = assistant_client
    async with factory() as session:
        thread = await create_thread(session, owner.id)
        first = await create_run(session, thread.id, owner.id, uuid4())
        second = await create_run(session, thread.id, owner.id, uuid4())

    await run_service.append_event(first.id, "user_message", {"content": "one"})
    await run_service.append_event(second.id, "user_message", {"content": "two"})

    response = await client.get(f"/v1/assistant/threads/{thread.id}/messages")
    events = response.json()

    assert [event["sequence"] for event in events] == [1, 1]
    assert {event["runId"] for event in events} == {str(first.id), str(second.id)}


async def test_run_recovery_returns_the_run_and_its_events_after_a_cursor(
    assistant_client,
):
    client, factory, owner = assistant_client
    async with factory() as session:
        thread = await create_thread(session, owner.id)
        run = await create_run(session, thread.id, owner.id, uuid4())

    await run_service.append_event(run.id, "token", {"content": "one"})
    await run_service.append_event(run.id, "token", {"content": "two"})

    response = await client.get(
        f"/v1/assistant/threads/{thread.id}/runs/{run.id}", params={"after": 1}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["threadId"] == str(thread.id)
    assert body["eventCursor"] == 2
    # `after` is exclusive, so the already-seen first token is not resent.
    assert [event["sequence"] for event in body["events"]] == [2]
    assert body["events"][0]["runId"] == str(run.id)
