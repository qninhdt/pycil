from datetime import UTC, datetime

import pytest
from sqlalchemy import delete

from pycil.app.config import load_config
from pycil.app.http import Problem
from pycil.library.access import readable, readable_path
from pycil.library.models import Node, NodePath, NodeRole, NodeSpace, NodeType
from pycil.library.nodes import create_node
from pycil.library.schemas import NodeCreate
from tests.support.account import account


async def test_visibility_uses_live_root_paths_and_public_breadcrumbs(database):
    owner, roots = await account(database.sessions)
    other, _ = await account(database.sessions)
    config = load_config()
    async with database.sessions() as session:
        private = await create_node(
            session, owner.id, NodeCreate(type=NodeType.DECK, name="Private"), config
        )
    async with database.sessions() as session:
        public = await create_node(
            session,
            owner.id,
            NodeCreate(
                type=NodeType.DECK,
                name="Public",
                parent_id=roots[NodeRole.PUBLISHED_ROOT].id,
                confirm_publication=True,
            ),
            config,
        )
    async with database.sessions() as session, session.begin():
        # A stale display-space label must never grant or revoke read authorization.
        (await session.get(Node, private["id"])).space = NodeSpace.PUBLISHED
        (await session.get(Node, public["id"])).space = NodeSpace.PERSONAL
    for viewer in [None, other.id]:
        async with database.sessions() as session:
            with pytest.raises(Problem) as error:
                await readable(session, private["id"], viewer, config)
            assert error.value.status == 404
        async with database.sessions() as session:
            node, path = await readable_path(session, public["id"], viewer, config)
            assert node.id == public["id"]
            assert [entry.id for entry in path] == [roots[NodeRole.PUBLISHED_ROOT].id, public["id"]]
    async with database.sessions() as session:
        assert (await readable(session, private["id"], owner.id, config)).id == private["id"]


@pytest.mark.parametrize("damage", ["deleted_ancestor", "detached"])
async def test_broken_physical_ancestry_denies_even_owner_reads(database, damage):
    owner, roots = await account(database.sessions)
    config = load_config()
    async with database.sessions() as session:
        folder = await create_node(
            session, owner.id, NodeCreate(type=NodeType.FOLDER, name="Parent"), config
        )
    async with database.sessions() as session:
        child = await create_node(
            session,
            owner.id,
            NodeCreate(type=NodeType.DECK, name="Child", parent_id=folder["id"]),
            config,
        )
    async with database.sessions() as session, session.begin():
        if damage == "deleted_ancestor":
            (await session.get(Node, folder["id"])).deleted_at = datetime.now(UTC)
        else:
            await session.execute(
                delete(NodePath).where(
                    NodePath.ancestor_id == roots[NodeRole.LIBRARY_ROOT].id,
                    NodePath.descendant_id == child["id"],
                )
            )
    async with database.sessions() as session:
        with pytest.raises(Problem) as error:
            await readable(session, child["id"], owner.id, config)
        assert error.value.code == "node_not_found"
