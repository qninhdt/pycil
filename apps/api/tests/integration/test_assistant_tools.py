"""Real-store task tools: bounded reads, batch SQL and atomic writes."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text

from pycil.assistant.tools import tools
from pycil.dependencies import process_resources
from pycil.http import Problem
from pycil.library.models import Node, NodeRole
from pycil.library.nodes import create_node
from pycil.library.schemas import NodeCreate
from pycil.library.tree import roots
from pycil.study.models import UserSense


@pytest.fixture
async def runtime(config, deployment, no_inference, senses):
    async with process_resources(config, deployment) as value:
        yield value


async def test_search_merges_queries_and_returns_usable_senses(runtime, user, senses, config):
    surface = {t.name: t for t in tools(runtime, user, config)}
    result = await surface["search_words"].ainvoke(
        {"queries": ["bank", "bank", "ban", "zzzz-no-match"], "limit": 1}
    )
    assert len(result["items"]) == 1
    hit = result["items"][0]
    assert hit["word_id"] == 1 and hit["matched_queries"] == ["bank", "ban"]
    assert [s["sense_id"] for s in hit["senses"]] == senses
    assert hit["senses"][0]["definition"] == "a financial institution"
    assert result["unmatched_queries"] == ["zzzz-no-match"]


async def test_vocabulary_and_scope_enrichment_do_not_query_per_result(
    runtime, database, user, senses, config
):
    async with database[0].begin() as connection:
        await connection.execute(
            text("""INSERT INTO lexi.words(id,lemma,match_key,entry_type,generation_state)
            SELECT n,'term-'||n,'term-'||n,'WORD','DONE' FROM generate_series(10,29) n""")
        )
        await connection.execute(
            text("""INSERT INTO lexi.senses(id,word_id,pos,tier)
            SELECT n,10+(n-100)/6,'NOUN','CORE' FROM generate_series(100,219) n""")
        )
        await connection.execute(
            text("""INSERT INTO lexi.definitions(sense_id,content)
            SELECT n,'meaning-'||n FROM generate_series(100,219) n""")
        )
    decks = []
    for index in range(10):
        async with runtime.sessions() as session:
            decks.append(
                await create_node(
                    session,
                    user.id,
                    NodeCreate(type="DECK", name=f"batch {index}", sense_ids=[1, 2]),
                    config,
                )
            )
    surface = {t.name: t for t in tools(runtime, user, config)}
    statements = []
    engines = [runtime.engine.sync_engine, runtime.lexicon.db.engine.sync_engine]

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    for engine in engines:
        event.listen(engine, "before_cursor_execute", capture)
    try:
        counts = []
        for ids in ([1], list(range(10, 30))):
            statements.clear()
            result = await surface["read_vocabulary"].ainvoke(
                {"word_ids": ids, "include": ["examples", "learning", "sources"]}
            )
            counts.append(len(statements))
            assert len(result["senses"]) == (2 if ids == [1] else 120)
        assert counts[1] <= counts[0] + 1, counts
        counts = []
        for ids in ([decks[0]["id"]], [d["id"] for d in reversed(decks)]):
            statements.clear()
            result = await surface["learning_overview"].ainvoke(
                {"node_ids": [str(i) for i in ids], "include": ["schedule"]}
            )
            counts.append(len(statements))
            assert [s["node_id"] for s in result["summaries"]] == [str(i) for i in ids]
            assert [s["node_id"] for s in result["schedules"]] == [str(i) for i in ids]
        assert counts[1] == counts[0], counts
        counts = []
        for limit in (1, 10):
            statements.clear()
            result = await surface["search_nodes"].ainvoke({"queries": ["batch"], "limit": limit})
            counts.append(len(statements))
            assert len(result["nodes"]) == limit
            assert all(n["summary"]["total"] == 2 for n in result["nodes"])
        assert counts[1] == counts[0], counts
    finally:
        for engine in engines:
            event.remove(engine, "before_cursor_execute", capture)


async def test_library_content_pages_by_mastery_and_rejects_changed_cursor(
    runtime, user, senses, config
):
    now = datetime.now(UTC)
    async with runtime.sessions() as session:
        deck = await create_node(
            session, user.id, NodeCreate(type="DECK", name="hello", sense_ids=senses), config
        )
    async with runtime.sessions() as session, session.begin():
        session.add(
            UserSense(
                user_id=user.id,
                sense_id=2,
                stability=1,
                difficulty=5,
                elo=-10,
                due_at=now + timedelta(days=1),
                last_exposure_at=now,
                review_count=1,
                lapse_count=0,
            )
        )
    read = next(t for t in tools(runtime, user, config) if t.name == "read_library")
    args = {"node_id": str(deck["id"]), "sort": "MASTERY_ASC", "limit": 1}
    first = await read.ainvoke(args)
    assert first["summary"]["total"] == 2 and first["senses"][0]["sense_id"] == 2
    assert first["next_cursor"]
    second = await read.ainvoke(args | {"cursor": first["next_cursor"]})
    assert second["senses"][0]["sense_id"] == 1 and second["next_cursor"] is None
    assert second["senses"][0]["learning"]["state"] == "NEW"
    with pytest.raises(Problem, match="invalid_cursor"):
        await read.ainvoke(args | {"cursor": first["next_cursor"], "state": "NEW"})
    assert first["node"]["path"][-1] == {"node_id": str(deck["id"]), "name": "hello"}


async def test_update_is_atomic_and_batch_failures_do_not_hide_successes(
    runtime, user, senses, config
):
    surface = {t.name: t for t in tools(runtime, user, config)}
    created = await surface["create_node"].ainvoke(
        {"name": "original", "type": "DECK", "sense_ids": [1]}
    )
    identifier = created["node_id"]
    await surface["update_node"].ainvoke(
        {"node_id": str(identifier), "description": "preserve this"}
    )
    membership = await surface["update_node"].ainvoke(
        {
            "node_id": str(identifier),
            "name": None,
            "description": None,
            "clear_description": False,
            "add_sense_ids": [2],
            "remove_sense_ids": [],
        }
    )
    assert membership["name"] == "original"
    assert membership["description"] == "preserve this"
    cleared = await surface["update_node"].ainvoke(
        {"node_id": str(identifier), "clear_description": True, "remove_sense_ids": [2]}
    )
    assert cleared["description"] is None
    with pytest.raises(Problem, match="sense_not_found"):
        await surface["update_node"].ainvoke(
            {"node_id": str(identifier), "name": "must roll back", "add_sense_ids": [999999]}
        )
    async with runtime.sessions() as session:
        assert (await session.get(Node, UUID(identifier))).name == "original"
    saved = await surface["update_node"].ainvoke(
        {
            "node_id": str(identifier),
            "name": "changed",
            "add_sense_ids": [2],
            "remove_sense_ids": [1],
        }
    )
    assert saved["name"] == "changed" and saved["added_count"] == saved["removed_count"] == 1
    assert saved["summary"]["total"] == 1
    async with runtime.sessions() as session:
        personal = (await roots(session, user.id))[NodeRole.PERSONAL_ROOT].id
    copied = await surface["copy_nodes"].ainvoke(
        {"node_ids": [str(identifier), str(uuid4())], "parent_id": str(personal)}
    )
    assert [r["status"] for r in copied["items"]] == ["SUCCEEDED", "FAILED"]
    assert copied["items"][0]["node_id"] != identifier
    assert copied["items"][0]["summary"]["total"] == 1
    assert copied["items"][1]["error"] == "node_not_found"
    saved = await surface["update_preferences"].ainvoke({"timezone": "Asia/Ho_Chi_Minh"})
    assert saved["settings"]["timezone"] == "Asia/Ho_Chi_Minh"
    assert not saved["settings"]["assistant"]["auto_approve"]
    assert saved["effective_learning"]["formats"] == ["SINGLE_CHOICE"]


async def test_agent_generation_uses_words_and_returns_json_tool_messages(
    runtime, user, senses, config, monkeypatch
):
    surface = {t.name: t for t in tools(runtime, user, config)}
    searches = []
    original = runtime.lexicon.search

    async def search(query, **values):
        searches.append(values.get("include_reference", False))
        return await original(query, **values)

    monkeypatch.setattr(runtime.lexicon, "search", search)
    found = await surface["search_words"].ainvoke({"queries": ["bank"], "limit": 1})
    assert all(item["kind"] == "WORD" and "reference_id" not in item for item in found["items"])
    assert searches == [False]
    generated = await surface["generate_words"].ainvoke(
        {
            "name": "generate_words",
            "id": "generate",
            "type": "tool_call",
            "args": {"words": ["bank", "bank"]},
        }
    )
    assert generated.status == "success"
    output = json.loads(generated.content)
    assert len(output["items"]) == 1
    item = output["items"][0]
    assert item["status"] == "SUCCEEDED" and item["lemma"] == "bank"
    assert item["task_id"] and [s["sense_id"] for s in item["senses"]] == senses
    assert "reference_id" not in item
    polled = await surface["get_generations"].ainvoke({"task_ids": [item["task_id"]]})
    assert polled["items"][0]["word_id"] == item["word_id"]
    invalid = await surface["generate_words"].ainvoke(
        {
            "name": "generate_words",
            "id": "invalid",
            "type": "tool_call",
            "args": {"entries": [{"reference_id": "arbitrary", "target": "English"}]},
        }
    )
    assert invalid.status == "error"
    assert json.loads(invalid.content)["error"] == "invalid_tool_arguments"


async def test_tool_validation_reports_fields_and_saved_metadata_is_json_safe(
    runtime, user, config
):
    surface = {t.name: t for t in tools(runtime, user, config)}
    created = await surface["create_node"].ainvoke(
        {
            "name": "create_node",
            "id": "create",
            "type": "tool_call",
            "args": {"name": "Hogwarts", "type": "DECK"},
        }
    )
    data = json.loads(created.content)
    assert data["node_id"] and data["summary"]["as_of"]
    assert created.status == "success"
    for args, field in [
        ({"name": " "}, "name must not be blank"),
        ({"description": "keep", "clear_description": True}, "not both"),
        ({"name": None, "description": None}, "membership change"),
    ]:
        result = await surface["update_node"].ainvoke(
            {
                "name": "update_node",
                "id": "update",
                "type": "tool_call",
                "args": {"node_id": data["node_id"], **args},
            }
        )
        assert result.status == "error"
        feedback = json.loads(result.content)
        assert feedback["error"] == "invalid_tool_arguments"
        assert field in feedback["details"][0]["msg"]
        assert "input" not in feedback["details"][0]


async def test_subtree_copy_reads_are_batched(runtime, user, senses, config):
    from pycil.library.nodes import copy_node
    from pycil.library.schemas import NodeDestination

    async def create(**values):
        async with runtime.sessions() as session:
            return await create_node(session, user.id, NodeCreate(**values), config)

    folders = []
    for size in (1, 10):
        folder = await create(type="FOLDER", name=f"copy {size}")
        folders.append(folder)
        for index in range(size):
            await create(
                type="DECK", name=f"deck {index}", parent_id=folder["id"], sense_ids=senses
            )
    async with runtime.sessions() as session:
        parent = (await roots(session, user.id))[NodeRole.PERSONAL_ROOT].id
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    engine = runtime.engine.sync_engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        counts = []
        for folder in folders:
            statements.clear()
            async with runtime.sessions() as session:
                copied = await copy_node(
                    session, user.id, folder["id"], NodeDestination(parent_id=parent), config
                )
            counts.append(len(statements))
            assert copied["id"] != folder["id"]
        assert counts[0] == counts[1], counts
    finally:
        event.remove(engine, "before_cursor_execute", capture)
