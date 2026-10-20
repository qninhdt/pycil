from time import monotonic

import pytest

from pycil.app.config import load_config
from pycil.app.http import status_for
from pycil.library.access import readable
from pycil.library.models import NodeRole, NodeType
from pycil.library.nodes import create_node, move_node
from pycil.library.schemas import NodeCreate, NodeMove
from pycil.library.scope import ScopeBudget, bounded, resolve_scopes
from pycil.library.search import search_nodes
from pycil.utils.errors import OperationError
from tests.support.account import account
from tests.support.vocabulary import neutral_word


@pytest.mark.parametrize("materialize", [False, True])
async def test_reused_scope_queries_keep_viewers_and_publication_live(database, materialize):
    config = load_config().library
    owner, roots = await account(database.sessions)
    stranger, _ = await account(database.sessions)
    async with database.sessions() as session:
        deck = await create_node(
            session, owner.id, NodeCreate(type=NodeType.DECK, name="Private"), config
        )
    for public in (False, True, False):
        async with database.sessions() as session:
            deck = await move_node(
                session,
                owner.id,
                deck["id"],
                NodeMove(
                    parent_id=roots[
                        NodeRole.PUBLISHED_ROOT if public else NodeRole.PERSONAL_ROOT
                    ].id,
                    confirm_publication=public,
                ),
                config,
            )
        for viewer in (owner.id, stranger.id, None, owner.id):
            async with database.sessions() as session:
                if public or viewer == owner.id:
                    scopes = await resolve_scopes(
                        session,
                        [deck["id"]],
                        viewer,
                        config,
                        materialize_candidates=materialize,
                    )
                    assert scopes[deck["id"]].decks == {deck["id"]}
                else:
                    with pytest.raises(OperationError) as error:
                        await resolve_scopes(session, [deck["id"]], viewer, config)
                    assert status_for(error.value) == 404


async def test_logical_reference_cycle_terminates_and_membership_is_distinct(database):
    config = load_config()
    user, _ = await account(database.sessions)
    _, sense = await neutral_word(database.sessions)

    async def create(kind, name, **extra):
        async with database.sessions() as session:
            return await create_node(
                session,
                user.id,
                NodeCreate(type=kind, name=name, **extra),
                config.library,
            )

    a = await create(NodeType.FOLDER, "A")
    b = await create(NodeType.FOLDER, "B")
    deck = await create(NodeType.DECK, "Finance", parent_id=b["id"], sense_ids=[sense])
    await create(NodeType.REFERENCE, "to B", parent_id=a["id"], reference_id=b["id"])
    await create(NodeType.REFERENCE, "to A", parent_id=b["id"], reference_id=a["id"])
    async with database.sessions() as session:
        scopes = await resolve_scopes(
            session,
            [a["id"], b["id"]],
            user.id,
            config.library,
        )
        assert scopes[a["id"]].decks == scopes[b["id"]].decks == {deck["id"]}
        assert list(await session.scalars(scopes[a["id"]].senses())) == [sense]
    tiny = config.model_copy(
        update={"library": config.library.model_copy(update={"max_scope_nodes": 2})}
    )
    async with database.sessions() as session:
        with pytest.raises(OperationError) as error:
            await resolve_scopes(
                session,
                [a["id"]],
                user.id,
                tiny.library,
            )
        assert error.value.code == "scope_too_large"
    async with database.sessions() as session:
        expired = ScopeBudget(
            user.id, started_at=monotonic() - config.library.scope_timeout_seconds - 1
        )
        with pytest.raises(OperationError) as error:
            async with bounded(session, config.library, expired):
                pytest.fail("expired request entered scope work")
        assert error.value.code == "scope_timeout"


async def test_discovery_is_public_only_and_scoped_fts_is_live_authorized(database):
    config = load_config()
    owner, roots = await account(database.sessions)
    stranger, _ = await account(database.sessions)
    async with database.sessions() as session:
        private = await create_node(
            session,
            owner.id,
            NodeCreate(type=NodeType.DECK, name="Finance private"),
            config.library,
        )
    async with database.sessions() as session:
        public = await create_node(
            session,
            owner.id,
            NodeCreate(
                type=NodeType.DECK,
                name="Finance public",
                parent_id=roots[NodeRole.PUBLISHED_ROOT].id,
                confirm_publication=True,
            ),
            config.library,
        )
    for viewer in (None, owner.id, stranger.id, None):
        async with database.sessions() as session:
            discovered = await search_nodes(session, viewer, config.library, q="Finance")
            assert [item["id"] for item in discovered["nodes"]] == [public["id"]]
    async with database.sessions() as session:
        personal = await search_nodes(
            session, owner.id, config.library, q="Finance", node_id=roots[NodeRole.PERSONAL_ROOT].id
        )
        assert [item["id"] for item in personal["nodes"]] == [private["id"]]
    async with database.sessions() as session:
        with pytest.raises(OperationError) as error:
            await search_nodes(
                session,
                stranger.id,
                config.library,
                q="Finance",
                node_id=roots[NodeRole.PERSONAL_ROOT].id,
            )
        assert status_for(error.value) == 404

    async with database.sessions() as session:
        await move_node(
            session,
            owner.id,
            public["id"],
            NodeMove(parent_id=roots[NodeRole.PERSONAL_ROOT].id),
            config.library,
        )
    for viewer in (stranger.id, owner.id, None):
        async with database.sessions() as session:
            assert not (await search_nodes(session, viewer, config.library, q="Finance"))["nodes"]


async def test_detached_private_ancestry_cannot_be_made_public_by_changing_space_label(database):
    from pycil.library.models import Node, NodeSpace

    config = load_config()
    owner, _ = await account(database.sessions)
    async with database.sessions() as session:
        deck = await create_node(
            session,
            owner.id,
            NodeCreate(type=NodeType.DECK, name="private"),
            config.library,
        )
    async with database.sessions() as session, session.begin():
        row = await session.get(Node, deck["id"])
        row.space = NodeSpace.PUBLISHED
    async with database.sessions() as session:
        with pytest.raises(OperationError) as error:
            await readable(session, deck["id"], None)
        assert status_for(error.value) == 404
        assert not (await search_nodes(session, None, config.library))["nodes"]
