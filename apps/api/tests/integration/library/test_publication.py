import pytest
from sqlalchemy import func, select

from pycil.app.config import load_config
from pycil.app.http import Problem
from pycil.library.access import readable
from pycil.library.models import Node, NodeRole, NodeSpace, NodeType
from pycil.library.nodes import copy_node, create_node, move_node
from pycil.library.schemas import NodeCreate, NodeDestination, NodeMove
from pycil.library.senses import member_ids
from tests.support.account import account
from tests.support.vocabulary import neutral_word


async def test_publication_and_revocation_apply_to_reference_membership(database):
    config = load_config()
    owner, roots = await account(database.sessions)
    reader, _ = await account(database.sessions)
    _, sense_id = await neutral_word(database.sessions)
    async with database.sessions() as session:
        deck = await create_node(
            session,
            owner.id,
            NodeCreate(type=NodeType.DECK, name="Private", sense_ids=[sense_id]),
            config,
        )
    async with database.sessions() as session:
        with pytest.raises(Problem) as error:
            await readable(session, deck["id"], reader.id, config)
        assert error.value.status == 404

    async with database.sessions() as session:
        with pytest.raises(Problem) as error:
            await move_node(
                session,
                owner.id,
                deck["id"],
                NodeMove(parent_id=roots[NodeRole.PUBLISHED_ROOT].id),
                config,
            )
        assert error.value.status == 409
    async with database.sessions() as session:
        published = await move_node(
            session,
            owner.id,
            deck["id"],
            NodeMove(parent_id=roots[NodeRole.PUBLISHED_ROOT].id, confirm_publication=True),
            config,
        )
        assert published["space"] == NodeSpace.PUBLISHED
    async with database.sessions() as session:
        reference = await create_node(
            session,
            reader.id,
            NodeCreate(type=NodeType.REFERENCE, name="Saved finance", reference_id=deck["id"]),
            config,
        )
    async with database.sessions() as session:
        node = await readable(session, reference["id"], reader.id, config)
        membership = await member_ids(session, node, reader.id, config)
        assert list(await session.scalars(membership)) == [sense_id]
    async with database.sessions() as session:
        await move_node(
            session,
            owner.id,
            deck["id"],
            NodeMove(parent_id=roots[NodeRole.PERSONAL_ROOT].id),
            config,
        )
    async with database.sessions() as session:
        node = await readable(session, reference["id"], reader.id, config)
        membership = await member_ids(session, node, reader.id, config)
        assert list(await session.scalars(membership)) == []
    async with database.sessions() as session:
        with pytest.raises(Problem) as error:
            await readable(session, deck["id"], reader.id, config)
        assert error.value.status == 404


async def test_publication_moves_internal_targets_atomically_and_retains_personal_link(database):
    config = load_config()
    user, roots = await account(database.sessions)
    _, sense_id = await neutral_word(database.sessions)
    async with database.sessions() as session:
        folder = await create_node(
            session, user.id, NodeCreate(type=NodeType.FOLDER, name="Shared tree"), config
        )
    async with database.sessions() as session:
        deck = await create_node(
            session,
            user.id,
            NodeCreate(
                type=NodeType.DECK, name="Deck", parent_id=folder["id"], sense_ids=[sense_id]
            ),
            config,
        )
    async with database.sessions() as session:
        await create_node(
            session,
            user.id,
            NodeCreate(
                type=NodeType.REFERENCE,
                name="Internal link",
                parent_id=folder["id"],
                reference_id=deck["id"],
            ),
            config,
        )
    async with database.sessions() as session:
        moved = await move_node(
            session,
            user.id,
            folder["id"],
            NodeMove(
                parent_id=roots[NodeRole.PUBLISHED_ROOT].id,
                confirm_publication=True,
                retain_personal_reference=True,
            ),
            config,
        )
    async with database.sessions() as session:
        public = await readable(session, folder["id"], None, config)
        assert public.space is NodeSpace.PUBLISHED
        assert list(await session.scalars(await member_ids(session, public, None, config))) == [
            sense_id
        ]
        retained = await readable(session, moved["retained_reference_id"], user.id, config)
        assert retained.space is NodeSpace.PERSONAL and retained.reference_id == folder["id"]
        assert retained.parent_id == roots[NodeRole.PERSONAL_ROOT].id
        with pytest.raises(Problem) as error:
            await readable(session, retained.id, None, config)
        assert error.value.status == 404


@pytest.mark.parametrize("operation", ["move", "copy"])
async def test_private_external_reference_rejects_publication_without_partial_subtree(
    database, operation
):
    config = load_config()
    user, roots = await account(database.sessions)
    async with database.sessions() as session:
        target = await create_node(
            session, user.id, NodeCreate(type=NodeType.DECK, name="Private target"), config
        )
    async with database.sessions() as session:
        folder = await create_node(
            session, user.id, NodeCreate(type=NodeType.FOLDER, name="Source"), config
        )
    async with database.sessions() as session:
        await create_node(
            session,
            user.id,
            NodeCreate(
                type=NodeType.REFERENCE,
                name="External private link",
                parent_id=folder["id"],
                reference_id=target["id"],
            ),
            config,
        )
    async with database.sessions() as session:
        count = await session.scalar(select(func.count()).select_from(Node))
    async with database.sessions() as session:
        with pytest.raises(Problem) as error:
            if operation == "move":
                await move_node(
                    session,
                    user.id,
                    folder["id"],
                    NodeMove(parent_id=roots[NodeRole.PUBLISHED_ROOT].id, confirm_publication=True),
                    config,
                )
            else:
                await copy_node(
                    session,
                    user.id,
                    folder["id"],
                    NodeDestination(
                        parent_id=roots[NodeRole.PUBLISHED_ROOT].id, confirm_publication=True
                    ),
                    config,
                )
        assert error.value.code == "private_reference_cannot_be_published"
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Node)) == count
        assert (await session.get(Node, folder["id"])).parent_id == roots[NodeRole.PERSONAL_ROOT].id
        with pytest.raises(Problem) as error:
            await readable(session, target["id"], None, config)
        assert error.value.status == 404
