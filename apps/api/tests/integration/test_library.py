import asyncio
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, text

from pycil.account.auth import actor, optional_actor
from pycil.account.models import User
from pycil.dependencies import process_resources
from pycil.http import Problem
from pycil.library.access import readable, scope_ids
from pycil.library.nodes import create_node, delete_node, node_details, save_node
from pycil.library.schemas import DeckSnapshot, NodeCreate, NodeSave
from pycil.library.senses import sense_page
from pycil.main import create_app


@pytest.fixture
async def resources(deployment, config, no_inference):
    async with process_resources(config, deployment) as value:
        yield value


async def create(sessions, user, config, **values):
    async with sessions() as session:
        return await create_node(session, user.id, NodeCreate(**values), config)


async def save(sessions, user, node, config, **changes):
    values = {k: node[k] for k in ("name", "description", "parent_id", "visibility")}
    if "sense_ids" in node:
        values["sense_ids"] = node["sense_ids"]
    async with sessions() as session:
        return await save_node(session, user.id, node["id"], NodeSave(**(values | changes)), config)


async def test_live_inheritance_reference_revocation_and_private_breadcrumbs(
    resources, user, config, senses, monkeypatch
):
    sessions, lexicon = resources.sessions, resources.lexicon
    root = await create(sessions, user, config, type="FOLDER", name="private")
    deck = await create(
        sessions,
        user,
        config,
        type="DECK",
        name="published",
        parent_id=root["id"],
        visibility="PUBLIC",
        confirm_publication=True,
        sense_ids=senses,
    )
    async with sessions() as session, session.begin():
        other = User(clerk_subject="viewer-" + uuid4().hex, settings={})
        session.add(other)
        await session.flush()
    reference = await create(
        sessions, other, config, type="REFERENCE", name="ref", reference_id=deck["id"]
    )
    async with sessions() as session:
        detail = await node_details(session, deck["id"], other.id, config, lexicon)
        assert detail["parent_id"] is None
        assert detail["breadcrumbs"] == [{"id": deck["id"], "name": "published"}]
        assert set(
            (await session.scalars(scope_ids(reference["id"], other.id, config))).all()
        ) == set(senses)
    snapshot = await resources.cache.get(f"deck:{deck['id']}", DeckSnapshot)
    assert snapshot.sense_ids == senses
    assert snapshot.parent_id == root["id"]  # Raw shared metadata is not an authorization result.
    assert set(snapshot.model_dump()) == {
        "id",
        "owner_id",
        "type",
        "name",
        "description",
        "parent_id",
        "visibility",
        "created_at",
        "updated_at",
        "sense_ids",
    }
    queries, native_queries = [], []

    def capture(_conn, _cursor, statement, *_):
        queries.append(statement)

    def capture_native(_conn, _cursor, statement, *_):
        native_queries.append(statement)

    event.listen(resources.engine.sync_engine, "before_cursor_execute", capture)
    event.listen(lexicon.db.engine.sync_engine, "before_cursor_execute", capture_native)
    try:
        async with sessions() as session:
            warm = await node_details(session, deck["id"], None, config, lexicon)
        assert warm["parent_id"] is None
        assert all(s["learning"] is None for s in warm["senses"])
        assert not any("deck_senses" in q or "sense_memory" in q for q in queries)
        assert native_queries == []
        warm["senses"][0]["lemma"] = "caller mutation"
        async with sessions() as session:
            assert (await node_details(session, deck["id"], other.id, config, lexicon))["senses"][
                0
            ]["lemma"] == "bank"
    finally:
        event.remove(resources.engine.sync_engine, "before_cursor_execute", capture)
        event.remove(lexicon.db.engine.sync_engine, "before_cursor_execute", capture_native)
    shared = await create(sessions, other, config, type="FOLDER", name="shared")
    linked = await create(sessions, other, config, type="FOLDER", name="linked")
    for folder, target in ((shared, linked), (linked, shared), (shared, deck), (linked, deck)):
        await create(
            sessions,
            other,
            config,
            type="REFERENCE",
            name="link",
            parent_id=folder["id"],
            reference_id=target["id"],
        )
    async with sessions() as session:
        identifiers = (await session.scalars(scope_ids(shared["id"], other.id, config))).all()
        assert set(identifiers) == set(senses)
    limited = config.model_copy(
        update={"library": config.library.model_copy(update={"page_size": 1})}
    )
    async with sessions() as session:
        folder = await readable(session, shared["id"], other.id, limited)
        first = await sense_page(session, folder, other.id, limited, lexicon)
        second = await sense_page(
            session, folder, other.id, limited, lexicon, first["next_after_id"]
        )
        assert [s["sense_id"] for s in first["senses"]] == [1]
        assert [s["sense_id"] for s in second["senses"]] == [2]
        assert second["next_after_id"] is None
    await save(sessions, user, deck, config, visibility="PRIVATE")
    assert await resources.cache.get(f"deck:{deck['id']}", DeckSnapshot) is None
    async with sessions() as session:
        with pytest.raises(Problem, match="node_not_found"):
            await readable(session, reference["id"], other.id, config)
        assert (await session.scalars(scope_ids(shared["id"], other.id, config))).all() == []
        with pytest.raises(Problem, match="node_not_found"):
            await node_details(session, deck["id"], other.id, config, lexicon)
    async with sessions() as session:
        await delete_node(session, other.id, reference["id"], config)


async def test_cycle_depth_ownership_and_membership_fk(resources, user, config, senses):
    sessions, lexicon = resources.sessions, resources.lexicon
    a = await create(sessions, user, config, type="FOLDER", name="a")
    b = await create(sessions, user, config, type="FOLDER", name="b", parent_id=a["id"])
    deck = await create(sessions, user, config, type="DECK", name="deck", parent_id=b["id"])
    with pytest.raises(Problem, match="collection_cycle"):
        await save(sessions, user, a, config, parent_id=b["id"])
    with pytest.raises(Problem, match="sense_not_found"):
        await save(sessions, user, deck, config, name="not committed", sense_ids=[99999])
    async with sessions() as session:
        detail = await node_details(session, deck["id"], user.id, config, lexicon)
        assert detail["name"] == "deck" and detail["senses"] == []
    deck = await save(sessions, user, deck, config, sense_ids=senses)
    statements = []

    def capture(_conn, _cursor, statement, *_):
        statements.append(statement)

    event.listen(resources.engine.sync_engine, "before_cursor_execute", capture)
    try:
        await save(sessions, user, deck, config)
    finally:
        event.remove(resources.engine.sync_engine, "before_cursor_execute", capture)
    assert not any(
        "deck_senses" in q and q.lstrip().startswith(("INSERT", "DELETE")) for q in statements
    )
    async with sessions() as session:
        assert (await node_details(session, a["id"], user.id, config, lexicon))["sense_count"] == 2
    assert config.library.max_senses_per_deck == 200
    async with sessions() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO lexi.senses(id,word_id,pos,tier) "
                "SELECT id,1,'NOUN','COMMON' FROM generate_series(3,203) AS id"
            )
        )
    deck = await save(sessions, user, deck, config, sense_ids=list(range(1, 200)))

    async def add(identifier):
        async with sessions() as session:
            try:
                await save_node(
                    session,
                    user.id,
                    deck["id"],
                    NodeSave(
                        name="deck",
                        visibility="PRIVATE",
                        parent_id=b["id"],
                        sense_ids=[*range(1, 200), identifier],
                    ),
                    config,
                )
                return "ok"
            except Problem as exc:
                return exc.code

    assert await asyncio.gather(add(200), add(201)) == ["ok", "ok"]
    async with sessions() as session:
        detail = await node_details(session, deck["id"], user.id, config, lexicon)
        assert detail["sense_count"] == len(detail["senses"]) == 200
        assert "sense_page" not in detail and "next_after_id" not in detail
        node = await readable(session, deck["id"], user.id, config)
        listing = await sense_page(session, node, None, config, lexicon)
        assert len(listing["senses"]) == 200
        assert all(s["learning"] is None for s in listing["senses"])
        with pytest.raises(Problem, match="deck_cursor_not_supported"):
            await sense_page(session, node, user.id, config, lexicon, 1)
        final = [s["sense_id"] for s in listing["senses"]]
        assert (200 in final) != (201 in final)  # Later successful final-state save wins.
    with pytest.raises(Problem, match="deck_sense_limit_exceeded"):
        await save(sessions, user, deck, config, sense_ids=[*final, 203])
    async with sessions() as session, session.begin():
        await session.execute(
            text("INSERT INTO deck_senses(deck_id,sense_id) VALUES(:deck,202)"),
            {"deck": deck["id"]},
        )
    await resources.cache.discard(f"deck:{deck['id']}")  # Raw fixture SQL bypasses native save.
    oversized = [*final, 202]
    deck = await save(sessions, user, deck, config, sense_ids=oversized, name="oversized")
    async with sessions() as session:
        assert (await node_details(session, deck["id"], user.id, config, lexicon))[
            "sense_count"
        ] == 201
    with pytest.raises(Problem, match="deck_sense_limit_exceeded"):
        await save(sessions, user, deck, config, sense_ids=[*oversized, 203])
    deck = await save(sessions, user, deck, config, sense_ids=final)
    deck = await save(sessions, user, deck, config, sense_ids=[])
    async with sessions() as session:
        assert (await node_details(session, deck["id"], user.id, config, lexicon))["senses"] == []
    async with sessions() as session:
        await delete_node(session, user.id, a["id"], config)
    async with sessions() as session:
        with pytest.raises(Problem, match="node_not_found"):
            await readable(session, deck["id"], user.id, config)


async def test_concurrent_opposing_moves_cannot_create_cycle(database, user, config):
    _, sessions, _ = database
    a = await create(sessions, user, config, type="FOLDER", name="a")
    b = await create(sessions, user, config, type="FOLDER", name="b")

    async def move(source, target):
        async with sessions() as session:
            try:
                await save_node(
                    session,
                    user.id,
                    source,
                    NodeSave(name="moved", visibility="PRIVATE", parent_id=target),
                    config,
                )
                return "ok"
            except Problem as error:
                return error.code

    assert sorted(await asyncio.gather(move(a["id"], b["id"]), move(b["id"], a["id"]))) == [
        "collection_cycle",
        "ok",
    ]


async def test_editor_http_contract_cache_outage_and_viewer_memory(
    resources, user, senses, config, monkeypatch
):
    from datetime import UTC, datetime, timedelta

    from redis.exceptions import ConnectionError

    from pycil.study.models import Rating, SenseMemory

    app = create_app()
    for name, value in vars(resources).items():
        setattr(app.state, name, value)
    app.state.product = config

    async def authenticated():
        return user

    app.dependency_overrides[actor] = authenticated
    app.dependency_overrides[optional_actor] = authenticated
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/v1/library/nodes",
            json={
                "type": "DECK",
                "name": "editor",
                "sense_ids": senses,
            },
        )
        assert created.status_code == 201, created.text
        url = "/v1/library/nodes/" + created.json()["id"]
        paths = app.openapi()["paths"]
        assert "put" in paths["/v1/library/nodes/{node_id}"]
        assert "patch" not in paths["/v1/library/nodes/{node_id}"]
        assert set(paths["/v1/library/nodes/{node_id}/senses"]) == {"get"}
        before = (await client.get(url)).json()
        bad = await client.put(
            url,
            json={
                "name": "failed",
                "visibility": "PRIVATE",
                "sense_ids": [99999],
            },
        )
        assert bad.status_code == 422
        assert (await client.get(url)).json() == before
        missing = await client.put(url, json={"name": "failed", "visibility": "PRIVATE"})
        assert missing.status_code == 422
        duplicate = await client.put(
            url,
            json={
                "name": "failed",
                "visibility": "PRIVATE",
                "sense_ids": [1, 1],
            },
        )
        assert duplicate.status_code == 422
        now = datetime.now(UTC)
        async with resources.sessions() as session, session.begin():
            session.add(
                SenseMemory(
                    user_id=user.id,
                    sense_id=1,
                    stability=10,
                    difficulty=5,
                    last_review_at=now - timedelta(days=1),
                    due_at=now - timedelta(seconds=1),
                    last_rating=Rating.GOOD,
                    review_count=1,
                    lapse_count=0,
                )
            )
        learned = (await client.get(url + "/senses")).json()["senses"]
        assert [s["learning"]["state"] for s in learned] == ["DUE", "NEW"]

        async def unavailable(*args, **kwargs):
            raise ConnectionError("optional cache unavailable")

        monkeypatch.setattr(resources.redis, "get", unavailable)
        monkeypatch.setattr(resources.redis, "eval", unavailable)
        from redis.asyncio.client import Pipeline

        monkeypatch.setattr(Pipeline, "execute", unavailable)
        assert (await client.get(url)).status_code == 200
        saved = await client.put(
            url,
            json={
                "name": "saved without cache",
                "visibility": "PRIVATE",
                "sense_ids": [],
            },
        )
        assert saved.status_code == 200
        empty = (await client.get(url)).json()
        assert empty["name"] == "saved without cache" and empty["sense_count"] == 0
        assert empty["senses"] == []
