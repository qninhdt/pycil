import asyncio
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import select, text

from pycil.library.access import readable
from pycil.library.models import Node, NodePath, NodeRole, NodeSpace
from pycil.library.scope import scope_ids
from pycil.library.tree import roots
from pycil.migrate import migrate, migration_config
from pycil.study.models import UserSense


async def legacy_user(connection, identifier):
    await connection.execute(
        text("""
        INSERT INTO users(id,clerk_subject,plan,settings,cycle_anchor,created_at)
        VALUES(:id,:subject,'FREE','{}',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
    """),
        {"id": identifier, "subject": str(identifier)},
    )


async def legacy_node(
    connection,
    identifier,
    owner,
    *,
    name,
    parent=None,
    kind="FOLDER",
    visibility="PRIVATE",
    target=None,
    deleted=False,
):
    await connection.execute(
        text("""
        INSERT INTO collection_nodes(id,owner_id,type,parent_id,reference_id,name,visibility,
                                     deleted_at,created_at,updated_at)
        VALUES(:id,:owner,:kind,:parent,:target,:name,:visibility,
               CASE WHEN :deleted THEN CURRENT_TIMESTAMP ELSE NULL END,
               CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
    """),
        {
            "id": identifier,
            "owner": owner,
            "kind": kind,
            "parent": parent,
            "target": target,
            "name": name,
            "visibility": visibility,
            "deleted": deleted,
        },
    )


@pytest.mark.parametrize("database", ["0001_baseline"], indirect=True)
async def test_populated_upgrade_preserves_effective_publication_identity_and_progress(
    database, config, senses
):
    engine, sessions, url = database
    owner, other = uuid4(), uuid4()
    private, public, deck, private_deck, bad_ref, foreign_deck, good_ref, deleted, hidden = [
        uuid4() for _ in range(9)
    ]
    async with engine.begin() as connection:
        for identifier in (owner, other):
            await legacy_user(connection, identifier)
        await legacy_node(connection, private, owner, name="secret parent")
        await legacy_node(
            connection, public, owner, name="public folder", parent=private, visibility="PUBLIC"
        )
        await legacy_node(
            connection, deck, owner, name="old PRIVATE-labelled child", parent=public, kind="DECK"
        )
        await legacy_node(connection, private_deck, owner, name="never publish", kind="DECK")
        await legacy_node(
            connection,
            bad_ref,
            owner,
            name="invalid public reference",
            parent=public,
            kind="REFERENCE",
            target=private_deck,
        )
        await legacy_node(
            connection, foreign_deck, other, name="foreign public", kind="DECK", visibility="PUBLIC"
        )
        await legacy_node(
            connection,
            good_ref,
            owner,
            name="valid public reference",
            parent=public,
            kind="REFERENCE",
            target=foreign_deck,
        )
        await legacy_node(connection, deleted, owner, name="deleted ancestor", deleted=True)
        await legacy_node(
            connection,
            hidden,
            owner,
            name="must not resurrect",
            parent=deleted,
            visibility="PUBLIC",
            kind="DECK",
        )
        await connection.execute(
            text("INSERT INTO deck_senses(deck_id,sense_id) VALUES(:deck,1),(:foreign,2)"),
            {"deck": deck, "foreign": foreign_deck},
        )
        await connection.execute(
            text("""
            INSERT INTO sense_memory(user_id,sense_id,stability,difficulty,last_review_at,due_at,
                                     last_rating,review_count,lapse_count,created_at,updated_at)
            VALUES(:owner,1,12,5,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,'GOOD',4,1,
                   CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
        """),
            {"owner": owner},
        )
    await asyncio.to_thread(migrate, url)
    await asyncio.to_thread(command.check, migration_config(url))
    async with sessions() as session:
        system = await roots(session, owner)
        assert set(system) == {
            NodeRole.LIBRARY_ROOT,
            NodeRole.PERSONAL_ROOT,
            NodeRole.PUBLISHED_ROOT,
        }
        published = await readable(session, public, None, config)
        assert published.parent_id == system[NodeRole.PUBLISHED_ROOT].id
        assert (await readable(session, deck, None, config)).space is NodeSpace.PUBLISHED
        assert (await session.get(Node, bad_ref)).parent_id == system[NodeRole.PERSONAL_ROOT].id
        assert (await session.get(Node, good_ref)).parent_id == public
        assert (await session.get(Node, private_deck)).space is NodeSpace.PERSONAL
        assert (await session.get(Node, hidden)).deleted_at is not None
        assert await session.get(NodePath, (hidden, hidden)) is None
        state = await session.get(UserSense, (owner, 1))
        assert (state.stability, state.review_count, state.lapse_count) == (12, 4, 1)
        query = await scope_ids(session, system[NodeRole.PUBLISHED_ROOT].id, None, config)
        assert set((await session.scalars(query)).all()) == {1, 2}
        # Private organization retains a reference, not a cloned deck or learning row.
        shortcut = await session.scalar(
            select(Node).where(Node.reference_id == public, Node.parent_id == private)
        )
        assert shortcut is not None and shortcut.space is NodeSpace.PERSONAL


@pytest.mark.parametrize("database", ["0001_baseline"], indirect=True)
async def test_invalid_old_ancestry_aborts_upgrade_without_changing_data(database):
    engine, _, url = database
    owner, a, b = uuid4(), uuid4(), uuid4()
    async with engine.begin() as connection:
        await legacy_user(connection, owner)
        await legacy_node(connection, a, owner, name="a")
        await legacy_node(connection, b, owner, name="b", parent=a)
        await connection.execute(
            text("UPDATE collection_nodes SET parent_id=:b WHERE id=:a"), {"a": a, "b": b}
        )
    with pytest.raises(RuntimeError, match="Cyclic or detached"):
        await asyncio.to_thread(command.upgrade, migration_config(url), "head")
    async with engine.connect() as connection:
        assert (
            await connection.scalar(text("SELECT version_num FROM public.alembic_version"))
            == "0001_baseline"
        )
        assert await connection.scalar(text("SELECT count(*) FROM collection_nodes")) == 2
        assert await connection.scalar(text("SELECT to_regclass('public.nodes')")) is None
