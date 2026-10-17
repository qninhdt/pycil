import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from pycil.app.config import load_config
from pycil.app.http import status_for
from pycil.library.models import DeckSense, Node, NodePath, NodeRole, NodeType
from pycil.library.nodes import (
    copy_node,
    create_node,
    delete_node,
    list_nodes,
    move_node,
    update_node,
)
from pycil.library.schemas import NodeCreate, NodeDestination, NodeMove, NodePatch, SenseDelta
from pycil.utils.errors import OperationError
from pycil.vocabulary.enums import PartOfSpeech, Tier
from pycil.vocabulary.models import Sense
from tests.support.account import account
from tests.support.vocabulary import neutral_word


@pytest.fixture
async def library(database):
    user, roots = await account(database.sessions)
    _, sense_id = await neutral_word(database.sessions)
    config = load_config()

    async def create(kind, name, **options):
        async with database.sessions() as session:
            return await create_node(
                session,
                user.id,
                NodeCreate(type=kind, name=name, **options),
                config.library,
            )

    return SimpleNamespace(user=user, roots=roots, sense=sense_id, config=config, create=create)


async def test_membership_is_idempotent_and_invalid_delta_rolls_back_metadata(database, library):
    deck = await library.create(NodeType.DECK, "Finance", description="original")

    async def patch(metadata=None, membership=None):
        async with database.sessions() as session:
            return await update_node(
                session,
                library.user.id,
                deck["id"],
                metadata,
                membership,
                library.config.library,
            )

    barrier = asyncio.Barrier(2)

    async def add_member():
        await barrier.wait()
        return await patch(membership=SenseDelta(add=[library.sense]))

    results = await asyncio.gather(
        add_member(),
        add_member(),
    )
    assert sum(result["added_count"] for result in results) == 1
    with pytest.raises(OperationError) as error:
        await patch(NodePatch(name="must roll back"), SenseDelta(add=[999999]))
    assert error.value.code == "sense_not_found"
    await patch(NodePatch(description=None))
    async with database.sessions() as session:
        saved = await session.get(Node, deck["id"])
        assert saved.name == "Finance"
        assert saved.description is None
        assert list(
            await session.scalars(select(DeckSense.sense_id).where(DeckSense.deck_id == saved.id))
        ) == [library.sense]
    removed = await patch(membership=SenseDelta(remove=[library.sense]))
    repeated = await patch(membership=SenseDelta(remove=[library.sense]))
    assert removed["removed_count"] == 1 and repeated["removed_count"] == 0


async def test_move_rebuilds_external_closure_preserves_internal_paths_and_rejects_cycles(
    database, library
):
    source = await library.create(NodeType.FOLDER, "Source")
    destination = await library.create(NodeType.FOLDER, "Destination")
    child = await library.create(
        NodeType.DECK, "Child", parent_id=source["id"], sense_ids=[library.sense]
    )
    async with database.sessions() as session:
        await move_node(
            session,
            library.user.id,
            source["id"],
            NodeMove(parent_id=destination["id"]),
            library.config.library,
        )
    async with database.sessions() as session:
        paths = {
            (a, d): depth
            for a, d, depth in (
                await session.execute(
                    select(NodePath.ancestor_id, NodePath.descendant_id, NodePath.depth)
                )
            ).all()
        }
        assert paths[destination["id"], child["id"]] == 2
        assert paths[source["id"], child["id"]] == 1
        assert paths[child["id"], child["id"]] == 0
        assert list(
            await session.scalars(
                select(DeckSense.sense_id).where(DeckSense.deck_id == child["id"])
            )
        ) == [library.sense]
    for parent in [source["id"], child["id"]]:
        async with database.sessions() as session:
            with pytest.raises(OperationError):
                await move_node(
                    session,
                    library.user.id,
                    source["id"],
                    NodeMove(parent_id=parent),
                    library.config.library,
                )
    async with database.sessions() as session:
        assert (await session.get(Node, source["id"])).parent_id == destination["id"]


async def test_copy_remaps_internal_references_and_memberships_independently(database, library):
    source = await library.create(NodeType.FOLDER, "Source")
    deck = await library.create(
        NodeType.DECK, "Deck", parent_id=source["id"], sense_ids=[library.sense]
    )
    await library.create(
        NodeType.REFERENCE, "Link", parent_id=source["id"], reference_id=deck["id"]
    )
    async with database.sessions() as session:
        copied = await copy_node(
            session,
            library.user.id,
            source["id"],
            NodeDestination(parent_id=library.roots[NodeRole.PERSONAL_ROOT].id),
            library.config.library,
        )
    async with database.sessions() as session:
        children = list(await session.scalars(select(Node).where(Node.parent_id == copied["id"])))
        clone_deck = next(n for n in children if n.type is NodeType.DECK)
        clone_link = next(n for n in children if n.type is NodeType.REFERENCE)
        assert clone_deck.id != deck["id"]
        assert clone_link.reference_id == clone_deck.id
        assert list(
            await session.scalars(
                select(DeckSense.sense_id).where(DeckSense.deck_id == clone_deck.id)
            )
        ) == [library.sense]
    async with database.sessions() as session:
        await update_node(
            session,
            library.user.id,
            clone_deck.id,
            None,
            SenseDelta(remove=[library.sense]),
            library.config.library,
        )
    async with database.sessions() as session:
        assert list(
            await session.scalars(select(DeckSense.sense_id).where(DeckSense.deck_id == deck["id"]))
        ) == [library.sense]


async def test_copy_quota_failure_leaves_no_partial_tree_and_deletion_releases_quota(
    database, library
):
    folder = await library.create(NodeType.FOLDER, "Folder")
    child = await library.create(NodeType.DECK, "Deck", parent_id=folder["id"])
    limited = library.config.model_copy(
        update={"library": library.config.library.model_copy(update={"max_owned_nodes": 5})}
    )
    async with database.sessions() as session:
        with pytest.raises(OperationError) as error:
            await copy_node(
                session,
                library.user.id,
                folder["id"],
                NodeDestination(parent_id=library.roots[NodeRole.PERSONAL_ROOT].id),
                limited.library,
            )
        assert error.value.code == "quota_exceeded"
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Node)) == 5
    async with database.sessions() as session:
        await delete_node(session, library.user.id, folder["id"])
    async with database.sessions() as session:
        assert (await session.get(Node, child["id"])).deleted_at is not None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(NodePath)
                .where(NodePath.descendant_id.in_([folder["id"], child["id"]]))
            )
            == 0
        )
    async with database.sessions() as session:
        created = await create_node(
            session,
            library.user.id,
            NodeCreate(type=NodeType.DECK, name="replacement"),
            limited.library,
        )
    assert created["deleted_at"] is None


async def test_system_roots_and_foreign_nodes_cannot_be_mutated(database, library):
    foreign, _ = await account(database.sessions)
    for owner, node in [
        (library.user.id, library.roots[NodeRole.PERSONAL_ROOT].id),
        (foreign.id, library.roots[NodeRole.PERSONAL_ROOT].id),
    ]:
        async with database.sessions() as session:
            with pytest.raises(OperationError) as error:
                await delete_node(session, owner, node)
            assert status_for(error.value) == (422 if owner == library.user.id else 404)


async def test_node_seek_survives_deleted_anchor_and_binds_parent_and_viewer(database, library):
    nodes = [await library.create(NodeType.DECK, name) for name in ["A", "B", "C"]]
    parent = library.roots[NodeRole.PERSONAL_ROOT].id
    async with database.sessions() as session:
        first = await list_nodes(
            session, library.user.id, parent, None, library.config.library, limit=1
        )
    token = first["next_cursor"]
    assert token
    async with database.sessions() as session:
        await delete_node(session, library.user.id, first["nodes"][0]["id"])
    async with database.sessions() as session:
        second = await list_nodes(
            session, library.user.id, parent, token, library.config.library, limit=5
        )
        assert {n["id"] for n in second["nodes"]} == {n["id"] for n in nodes} - {
            first["nodes"][0]["id"]
        }
    for viewer, scope in [
        (None, parent),
        (library.user.id, library.roots[NodeRole.PUBLISHED_ROOT].id),
    ]:
        async with database.sessions() as session:
            with pytest.raises(OperationError) as error:
                await list_nodes(session, viewer, scope, token, library.config.library)
            assert error.value.code == "invalid_cursor"


async def test_concurrent_growth_obeys_exact_node_quota(database, library):
    limited = library.config.model_copy(
        update={"library": library.config.library.model_copy(update={"max_owned_nodes": 3})}
    )
    barrier = asyncio.Barrier(2)

    async def create(name):
        await barrier.wait()
        async with database.sessions() as session:
            return await create_node(
                session,
                library.user.id,
                NodeCreate(type=NodeType.DECK, name=name),
                limited.library,
            )

    results = await asyncio.gather(create("A"), create("B"), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    failure = next(result for result in results if isinstance(result, OperationError))
    assert failure.code == "quota_exceeded"
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Node)) == 4


async def test_over_limit_memberships_allow_reduction_but_not_growth(database, library):
    async with database.sessions() as session, session.begin():
        word_id = (await session.get(Sense, library.sense)).word_id
        senses = [Sense(word_id=word_id, pos=PartOfSpeech.NOUN, tier=Tier.CORE) for _ in range(2)]
        session.add_all(senses)
        await session.flush()
        second, third = (sense.id for sense in senses)
    deck = await library.create(NodeType.DECK, "Deck", sense_ids=[library.sense, second])
    limited = library.config.model_copy(
        update={
            "library": library.config.library.model_copy(
                update={"max_senses_per_deck": 1, "max_owned_memberships": 1}
            )
        }
    )
    async with database.sessions() as session:
        repaired = await update_node(
            session,
            library.user.id,
            deck["id"],
            NodePatch(name="repaired"),
            SenseDelta(remove=[second]),
            limited.library,
        )
    assert repaired["sense_ids"] == [library.sense]
    async with database.sessions() as session:
        with pytest.raises(OperationError) as error:
            await update_node(
                session,
                library.user.id,
                deck["id"],
                NodePatch(name="must roll back"),
                SenseDelta(add=[third]),
                limited.library,
            )
        assert error.value.code == "deck_sense_limit_exceeded"
    async with database.sessions() as session:
        assert (await session.get(Node, deck["id"])).name == "repaired"
        assert list(
            await session.scalars(select(DeckSense.sense_id).where(DeckSense.deck_id == deck["id"]))
        ) == [library.sense]


async def test_move_respects_subtree_height_and_rejects_descendant_reference_to_new_ancestor(
    database, library
):
    source = await library.create(NodeType.FOLDER, "Source")
    child = await library.create(NodeType.DECK, "Child", parent_id=source["id"])
    destination = await library.create(NodeType.FOLDER, "Destination")
    limited = library.config.model_copy(
        update={"library": library.config.library.model_copy(update={"max_depth": 3})}
    )
    async with database.sessions() as session:
        with pytest.raises(OperationError) as error:
            await move_node(
                session,
                library.user.id,
                source["id"],
                NodeMove(parent_id=destination["id"]),
                limited.library,
            )
        assert error.value.code == "node_depth_exceeded"
    await library.create(
        NodeType.REFERENCE,
        "Would become ancestor reference",
        parent_id=source["id"],
        reference_id=destination["id"],
    )
    async with database.sessions() as session:
        with pytest.raises(OperationError) as error:
            await move_node(
                session,
                library.user.id,
                source["id"],
                NodeMove(parent_id=destination["id"]),
                library.config.library,
            )
        assert error.value.code == "node_cycle"
    async with database.sessions() as session:
        assert (await session.get(Node, source["id"])).parent_id == library.roots[
            NodeRole.PERSONAL_ROOT
        ].id
        assert (await session.get(Node, child["id"])).parent_id == source["id"]
