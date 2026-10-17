from types import SimpleNamespace

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from pycil.app.config import load_config
from pycil.app.http import status_for
from pycil.assistant.checkpoints import checkpoint_pool
from pycil.assistant.conversations import delete_conversation, guard
from pycil.assistant.graph import graph
from pycil.assistant.models import Conversation
from pycil.utils.errors import OperationError
from tests.support.account import account


class AssistantProvider(GenericFakeChatModel):
    def bind_tools(self, tools, **options):
        return self


async def test_native_checkpoint_survives_pool_restart_and_owned_delete_cleans_thread(
    database,
    redis_store,
):
    config = load_config()
    user, _ = await account(database.sessions)
    stranger, _ = await account(database.sessions)
    async with database.sessions() as session, session.begin():
        conversation = Conversation(user_id=user.id)
        session.add(conversation)
        await session.flush()
        identifier = conversation.id
    thread = {"configurable": {"thread_id": str(identifier)}}
    redis, _ = redis_store
    resources = SimpleNamespace(sessions=database.sessions, redis=redis)
    provider = AssistantProvider(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "update_preferences",
                            "args": {"locale": "vi"},
                            "id": "settings-call",
                        }
                    ],
                ),
                AIMessage(content="Your language preference is saved."),
            ]
        )
    )
    async with checkpoint_pool(database.url) as pool:
        resources.checkpoint_pool = pool
        agent = graph(resources, user.id, config, provider, auto_approve=True)
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content="Set my language to Vietnamese.")]},
            thread,
        )
        assert result["messages"][-1].content == "Your language preference is saved."
        tool_result = next(message for message in result["messages"] if message.type == "tool")
        assert '"locale": "vi"' in tool_result.content
    async with checkpoint_pool(database.url) as pool:
        resources.checkpoint_pool = pool
        restarted = graph(resources, user.id, config, provider)
        snapshot = await restarted.aget_state(thread)
        assert snapshot.values["messages"][-1].content == result["messages"][-1].content
        with pytest.raises(OperationError) as error:
            await delete_conversation(
                resources,
                stranger.id,
                identifier,
                lease_ttl=config.assistant.lease_ttl_seconds,
            )
        assert status_for(error.value) == 404
        assert await AsyncPostgresSaver(pool).aget_tuple(thread) is not None
        async with guard(redis, identifier, ttl=config.assistant.lease_ttl_seconds):
            with pytest.raises(OperationError) as error:
                await delete_conversation(
                    resources,
                    user.id,
                    identifier,
                    lease_ttl=config.assistant.lease_ttl_seconds,
                )
            assert status_for(error.value) == 409
        await delete_conversation(
            resources, user.id, identifier, lease_ttl=config.assistant.lease_ttl_seconds
        )
        assert await AsyncPostgresSaver(pool).aget_tuple(thread) is None
        async with database.sessions() as session:
            assert await session.get(Conversation, identifier) is None
