from types import SimpleNamespace

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from pycil.account.models import User
from pycil.app.config import load_config
from pycil.assistant.checkpoints import checkpoint_pool
from pycil.assistant.graph import graph
from pycil.assistant.models import Conversation
from pycil.assistant.tools import tools
from pycil.library.models import Node, NodeRole, NodeType
from pycil.library.nodes import create_node
from pycil.library.schemas import NodeCreate
from tests.support.account import account


class Provider(GenericFakeChatModel):
    def bind_tools(self, tools, **options):
        return self


@pytest.mark.parametrize("decision", ["approve", "reject"])
async def test_pending_mutation_persists_across_restart_and_executes_only_on_approval(
    database, decision
):
    user, _ = await account(database.sessions)
    config = load_config()
    async with database.sessions() as session, session.begin():
        conversation = Conversation(user_id=user.id)
        session.add(conversation)
        await session.flush()
        thread = {
            "configurable": {"thread_id": str(conversation.id), "reject_all": decision == "reject"}
        }
    resources = SimpleNamespace(sessions=database.sessions)
    provider = Provider(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "update_preferences",
                            "args": {"locale": "vi"},
                            "id": "save-locale",
                        }
                    ],
                ),
                AIMessage(content="Finished."),
            ]
        )
    )
    async with checkpoint_pool(database.url) as pool:
        resources.checkpoint_pool = pool
        agent = graph(resources, user.id, config, provider)
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content="Set my language to Vietnamese.")]}, thread
        )
        assert result["__interrupt__"]
        async with database.sessions() as session:
            assert (await session.get(User, user.id)).settings == {}
    async with checkpoint_pool(database.url) as pool:
        resources.checkpoint_pool = pool
        restarted = graph(resources, user.id, config, provider)
        state = await restarted.aget_state(thread)
        assert any(task.interrupts for task in state.tasks)
        resumed = await restarted.ainvoke(
            Command(resume={"decisions": [{"type": decision}]}), thread
        )
        assert not resumed.get("__interrupt__")
        async with database.sessions() as session:
            saved = (await session.get(User, user.id)).settings
        assert saved == ({"locale": "vi"} if decision == "approve" else {})
        assert any(message.type == "tool" for message in resumed["messages"])


async def test_tool_batch_commits_successful_items_and_reports_unauthorized_items(database):
    config = load_config()
    user, roots = await account(database.sessions)
    stranger, _ = await account(database.sessions)
    async with database.sessions() as session:
        owned = await create_node(
            session,
            user.id,
            NodeCreate(type=NodeType.DECK, name="mine"),
            config.library,
        )
    async with database.sessions() as session:
        foreign = await create_node(
            session,
            stranger.id,
            NodeCreate(type=NodeType.DECK, name="private"),
            config.library,
        )
    surface = {
        tool.name: tool
        for tool in tools(SimpleNamespace(sessions=database.sessions), user.id, config)
    }
    result = await surface["delete_nodes"].ainvoke(
        {"node_ids": [str(owned["id"]), str(foreign["id"]), str(roots[NodeRole.PERSONAL_ROOT].id)]}
    )
    assert [item["status"] for item in result["items"]] == ["succeeded", "failed", "failed"]
    assert result["items"][1]["error"] == "node_not_found"
    assert result["items"][2]["error"] == "system_node_protected"
    async with database.sessions() as session:
        assert (await session.get(Node, owned["id"])).deleted_at is not None
        assert (await session.get(Node, foreign["id"])).deleted_at is None
        assert (await session.get(Node, roots[NodeRole.PERSONAL_ROOT].id)).deleted_at is None
