from time import monotonic

import pytest

from pycil.app.config import load_config
from pycil.app.http import Problem
from pycil.library.access import readable
from pycil.library.models import NodeRole, NodeType
from pycil.library.nodes import create_node
from pycil.library.schemas import NodeCreate
from pycil.library.scope import ScopeBudget, bounded, resolve_scopes
from pycil.library.search import search_nodes
from tests.support.account import account
from tests.support.vocabulary import neutral_word


async def test_logical_reference_cycle_terminates_and_membership_is_distinct(database):
    config = load_config()
    user, _ = await account(database.sessions)
    _, sense = await neutral_word(database.sessions)

    async def create(kind, name, **extra):
        async with database.sessions() as session:
            return await create_node(
                session, user.id, NodeCreate(type=kind, name=name, **extra), config
            )

    a = await create(NodeType.FOLDER, "A")
    b = await create(NodeType.FOLDER, "B")
    deck = await create(NodeType.DECK, "Finance", parent_id=b["id"], sense_ids=[sense])
    await create(NodeType.REFERENCE, "to B", parent_id=a["id"], reference_id=b["id"])
    await create(NodeType.REFERENCE, "to A", parent_id=b["id"], reference_id=a["id"])
    async with database.sessions() as session:
        scopes = await resolve_scopes(session, [a["id"], b["id"]], user.id, config)
        assert scopes[a["id"]].decks == scopes[b["id"]].decks == {deck["id"]}
        assert list(await session.scalars(scopes[a["id"]].senses())) == [sense]
    tiny = config.model_copy(
        update={
            "product": config.product.model_copy(
                update={
                    "library": config.product.library.model_copy(
                        update={
                            "quotas": config.product.library.quotas.model_copy(
                                update={"max_scope_nodes": 2}
                            )
                        }
                    )
                }
            )
        }
    )
    async with database.sessions() as session:
        with pytest.raises(Problem) as error:
            await resolve_scopes(session, [a["id"]], user.id, tiny)
        assert error.value.code == "scope_too_large"
    async with database.sessions() as session:
        expired = ScopeBudget(
            user.id, started_at=monotonic() - config.runtime.library.scope_timeout_seconds - 1
        )
        with pytest.raises(Problem) as error:
            async with bounded(session, config, expired):
                pytest.fail("expired request entered scope work")
        assert error.value.code == "scope_timeout"


async def test_discovery_is_public_only_and_scoped_fts_is_live_authorized(database):
    config = load_config()
    owner, roots = await account(database.sessions)
    stranger, _ = await account(database.sessions)
    async with database.sessions() as session:
        private = await create_node(
            session, owner.id, NodeCreate(type=NodeType.DECK, name="Finance private"), config
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
            config,
        )
    async with database.sessions() as session:
        discovered = await search_nodes(session, None, config, q="Finance")
        assert [item["id"] for item in discovered["nodes"]] == [public["id"]]
    async with database.sessions() as session:
        personal = await search_nodes(
            session, owner.id, config, q="Finance", node_id=roots[NodeRole.PERSONAL_ROOT].id
        )
        assert [item["id"] for item in personal["nodes"]] == [private["id"]]
    async with database.sessions() as session:
        with pytest.raises(Problem) as error:
            await search_nodes(
                session, stranger.id, config, q="Finance", node_id=roots[NodeRole.PERSONAL_ROOT].id
            )
        assert error.value.status == 404


async def test_detached_private_ancestry_cannot_be_made_public_by_changing_space_label(database):
    from pycil.library.models import Node, NodeSpace

    config = load_config()
    owner, _ = await account(database.sessions)
    async with database.sessions() as session:
        deck = await create_node(
            session, owner.id, NodeCreate(type=NodeType.DECK, name="private"), config
        )
    async with database.sessions() as session, session.begin():
        row = await session.get(Node, deck["id"])
        row.space = NodeSpace.PUBLISHED
    async with database.sessions() as session:
        with pytest.raises(Problem) as error:
            await readable(session, deck["id"], None, config)
        assert error.value.status == 404
        assert not (await search_nodes(session, None, config))["nodes"]
