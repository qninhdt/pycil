import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import func, select

from pycil.account.models import UsageEvent, User
from pycil.app.config import load_config
from pycil.app.factory import create_app
from pycil.assistant import graph as agents
from pycil.assistant.checkpoints import checkpoint_pool
from pycil.assistant.stream import assistant_rate_limit_pattern
from tests.support.account import account


class Provider(GenericFakeChatModel):
    def bind_tools(self, tools, **options):
        return self


async def test_conversation_http_stream_state_pagination_and_delete_enforce_ownership(
    database, redis_store, monkeypatch
):
    owner, _ = await account(database.sessions)
    other, _ = await account(database.sessions)
    async with database.sessions() as session, session.begin():
        for actor, handle in [(owner, "owner"), (other, "other")]:
            saved = await session.get(User, actor.id)
            saved.display_name = saved.handle = handle

    class Identity:
        async def subject(self, token):
            return owner.clerk_id if token == "owner" else other.clerk_id

    provider = Provider(messages=iter([AIMessage(content="Hello learner.")]))

    @asynccontextmanager
    async def model(*args):
        yield provider

    monkeypatch.setattr(agents, "model", model)
    redis, _ = redis_store
    app = create_app()
    app.state.sessions = database.sessions
    app.state.config = load_config()
    app.state.identity = Identity()
    app.state.deployment = SimpleNamespace(allowed_origins=[])
    app.state.redis = redis
    headers = {"Authorization": "Bearer owner"}
    foreign = {"Authorization": "Bearer other"}
    try:
        async with checkpoint_pool(database.url) as pool:
            app.state.checkpoint_pool = pool
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://api.test"
            ) as client:
                created = await client.post(
                    "/v1/assistant/conversations", headers=headers, json={"title": "First"}
                )
                assert created.status_code == 201
                identifier = created.json()["id"]
                await client.post(
                    "/v1/assistant/conversations", headers=headers, json={"title": "Second"}
                )
                first = await client.get("/v1/assistant/conversations?limit=1", headers=headers)
                cursor = first.json()["next_cursor"]
                assert cursor and len(first.json()["conversations"]) == 1
                second = await client.get(
                    "/v1/assistant/conversations", headers=headers, params={"cursor": cursor}
                )
                assert len(second.json()["conversations"]) == 1
                assert {
                    row["title"] for page in [first, second] for row in page.json()["conversations"]
                } == {"First", "Second"}
                assert (
                    await client.get(
                        "/v1/assistant/conversations", headers=foreign, params={"cursor": cursor}
                    )
                ).status_code == 422
                payload = dict(
                    thread_id=identifier,
                    run_id=str(uuid4()),
                    state={},
                    tools=[],
                    context=[],
                    messages=[{"id": "user-message", "role": "user", "content": "Hello"}],
                )
                denied = await client.post("/v1/assistant:run", headers=foreign, json=payload)
                assert denied.status_code == 404
                streamed = await client.post("/v1/assistant:run", headers=headers, json=payload)
                assert streamed.status_code == 200
                assert streamed.headers["content-type"].startswith("text/event-stream")
                assert streamed.headers["cache-control"] == "no-cache, no-transform"
                assert streamed.headers["x-accel-buffering"] == "no"
                events = [
                    json.loads(line.removeprefix("data: "))
                    for line in streamed.text.splitlines()
                    if line.startswith("data: ")
                ]
                assert events[0]["type"] == "RUN_STARTED" and events[-1]["type"] == "RUN_FINISHED"
                details = await client.get(
                    f"/v1/assistant/conversations/{identifier}", headers=headers
                )
                assert details.status_code == 200
                assert details.json()["state"]["messages"][-1]["content"] == "Hello learner."
                for method in [client.get, client.delete]:
                    assert (
                        await method(f"/v1/assistant/conversations/{identifier}", headers=foreign)
                    ).status_code == 404
                assert (
                    await client.delete(
                        f"/v1/assistant/conversations/{identifier}", headers=headers
                    )
                ).status_code == 204
                assert (
                    await AsyncPostgresSaver(pool).aget_tuple(
                        {"configurable": {"thread_id": identifier}}
                    )
                    is None
                )
                assert (
                    await client.get(f"/v1/assistant/conversations/{identifier}", headers=headers)
                ).status_code == 404
        async with database.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(UsageEvent)) == 1
    finally:
        keys = [key async for key in redis.scan_iter(match=assistant_rate_limit_pattern(owner.id))]
        if keys:
            await redis.delete(*keys)
