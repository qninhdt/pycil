import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select, text

from pycil.account.auth import actor, optional_actor
from pycil.account.models import User
from pycil.dependencies import process_resources
from pycil.http import Problem
from pycil.library.access import readable
from pycil.library.models import Node, NodePath, NodeRole
from pycil.library.nodes import (
    copy_node,
    create_node,
    delete_node,
    list_nodes,
    move_node,
    node_details,
    patch_node,
    patch_senses,
)
from pycil.library.schemas import (
    NodeCreate,
    NodeDestination,
    NodeMove,
    NodePatch,
    SenseDelta,
)
from pycil.library.scope import ScopeBudget, scope_ids
from pycil.library.senses import sense_page
from pycil.library.tree import provision_library, roots
from pycil.main import create_app
from pycil.study.models import UserSense


@pytest.fixture
async def resources(deployment, config, no_inference):
    async with process_resources(config, deployment) as value:
        yield value


async def create(sessions, user, config, **values):
    async with sessions() as session:
        return await create_node(session, user.id, NodeCreate(**values), config)


async def move_to(sessions, user, node, config, **changes):
    async with sessions() as session:
        return await move_node(session, user.id, node["id"], NodeMove(**changes), config)


async def system_roots(sessions, user):
    async with sessions() as session:
        return await roots(session, user.id)


async def other_user(sessions):
    async with sessions() as session, session.begin():
        user = User(clerk_subject="viewer-" + uuid4().hex, settings={})
        session.add(user)
        await session.flush()
        await provision_library(session, user.id)
        return user


async def ids(sessions, node_id, viewer_id, config, budget=None):
    async with sessions() as session:
        query = await scope_ids(session, node_id, viewer_id, config, budget=budget)
        return set((await session.scalars(query)).all())


async def test_system_roles_and_whole_library_tracking(database, user, config, senses):
    _, sessions, _ = database
    system = await system_roots(sessions, user)
    assert set(system) == {NodeRole.LIBRARY_ROOT, NodeRole.PERSONAL_ROOT, NodeRole.PUBLISHED_ROOT}
    personal = await create(sessions, user, config, type="DECK", name="private", sense_ids=senses)
    published = await create(
        sessions,
        user,
        config,
        type="DECK",
        name="public",
        sense_ids=senses,
        parent_id=system[NodeRole.PUBLISHED_ROOT].id,
        confirm_publication=True,
    )
    assert personal["parent_id"] == system[NodeRole.PERSONAL_ROOT].id
    assert await ids(sessions, None, user.id, config) == set(senses)
    assert await ids(sessions, published["id"], None, config) == set(senses)
    for root in system.values():
        with pytest.raises(Problem, match="system_node_protected"):
            async with sessions() as session:
                await delete_node(session, user.id, root.id, config)
        with pytest.raises(Problem, match="system_node_protected"):
            async with sessions() as session:
                await patch_node(session, user.id, root.id, NodePatch(name="changed"), config)
    with pytest.raises(Problem, match="invalid_parent"):
        await create(
            sessions,
            user,
            config,
            type="FOLDER",
            name="invalid",
            parent_id=system[NodeRole.LIBRARY_ROOT].id,
        )
    async with sessions() as session:
        for node_id in (
            system[NodeRole.LIBRARY_ROOT].id,
            system[NodeRole.PERSONAL_ROOT].id,
            personal["id"],
        ):
            with pytest.raises(Problem, match="node_not_found"):
                await readable(session, node_id, None, config)
        path_depth = await session.scalar(
            select(NodePath.depth).where(
                NodePath.ancestor_id == system[NodeRole.LIBRARY_ROOT].id,
                NodePath.descendant_id == personal["id"],
            )
        )
        assert path_depth == 2


async def test_publication_move_reference_revocation_and_breadcrumbs(
    database, user, config, senses
):
    _, sessions, _ = database
    system = await system_roots(sessions, user)
    private = await create(sessions, user, config, type="FOLDER", name="private ancestor")
    folder = await create(
        sessions, user, config, type="FOLDER", name="publish me", parent_id=private["id"]
    )
    deck = await create(
        sessions, user, config, type="DECK", name="deck", parent_id=folder["id"], sense_ids=senses
    )
    with pytest.raises(Problem, match="publication_confirmation_required"):
        await move_to(sessions, user, folder, config, parent_id=system[NodeRole.PUBLISHED_ROOT].id)
    folder = await move_to(
        sessions,
        user,
        folder,
        config,
        parent_id=system[NodeRole.PUBLISHED_ROOT].id,
        confirm_publication=True,
        retain_personal_reference=True,
    )
    assert folder["retained_reference_id"] is not None
    assert await ids(sessions, None, user.id, config) == set(senses)
    async with sessions() as session:
        detail = await node_details(session, deck["id"], None, config)
        assert [crumb["name"] for crumb in detail["breadcrumbs"]] == [
            "Published",
            "publish me",
            "deck",
        ]
        assert "senses" not in detail and "sense_count" not in detail
        assert (await node_details(session, system[NodeRole.PUBLISHED_ROOT].id, None, config))[
            "parent_id"
        ] is None
    other = await other_user(sessions)
    reference = await create(
        sessions, other, config, type="REFERENCE", name="ref", reference_id=folder["id"]
    )
    assert await ids(sessions, None, other.id, config) == set(senses)
    async with sessions() as session:
        children = await list_nodes(session, None, folder["id"], None, config)
        assert [n["id"] for n in children["nodes"]] == [deck["id"]]
        linked_children = await list_nodes(session, other.id, reference["id"], None, config)
        assert [n["id"] for n in linked_children["nodes"]] == [deck["id"]]
    await move_to(sessions, user, folder, config, parent_id=system[NodeRole.PERSONAL_ROOT].id)
    assert await ids(sessions, None, other.id, config) == set()
    async with sessions() as session:
        unavailable = await node_details(session, reference["id"], other.id, config)
        assert unavailable["reference_available"] is False
        assert unavailable["reference_id"] is None
        with pytest.raises(Problem, match="node_not_found"):
            await readable(session, deck["id"], other.id, config)


async def test_published_references_never_publish_private_targets(database, user, config, senses):
    _, sessions, _ = database
    system = await system_roots(sessions, user)
    deck = await create(sessions, user, config, type="DECK", name="private", sense_ids=senses)
    folder = await create(sessions, user, config, type="FOLDER", name="folder")
    await create(
        sessions,
        user,
        config,
        type="REFERENCE",
        name="ref",
        parent_id=folder["id"],
        reference_id=deck["id"],
    )
    with pytest.raises(Problem, match="private_reference_cannot_be_published"):
        await move_to(
            sessions,
            user,
            folder,
            config,
            parent_id=system[NodeRole.PUBLISHED_ROOT].id,
            confirm_publication=True,
        )
    with pytest.raises(Problem, match="private_reference_cannot_be_published"):
        await create(
            sessions,
            user,
            config,
            type="REFERENCE",
            name="ref",
            parent_id=system[NodeRole.PUBLISHED_ROOT].id,
            reference_id=deck["id"],
            confirm_publication=True,
        )
    # Same-subtree targets become published in the same canonical move.
    deck = await move_to(sessions, user, deck, config, parent_id=folder["id"])
    folder = await move_to(
        sessions,
        user,
        folder,
        config,
        parent_id=system[NodeRole.PUBLISHED_ROOT].id,
        confirm_publication=True,
    )
    assert await ids(sessions, folder["id"], None, config) == set(senses)
    await move_to(sessions, user, deck, config, parent_id=system[NodeRole.PERSONAL_ROOT].id)
    assert await ids(sessions, folder["id"], user.id, config) == set()
    # The publisher's private privilege cannot revive the Published alias.
    async with sessions() as session, session.begin():
        await session.execute(
            text("UPDATE nodes SET space='PERSONAL' WHERE parent_id=:folder"),
            {"folder": folder["id"]},
        )
    assert await ids(sessions, folder["id"], user.id, config) == set()


async def test_physical_closure_cycles_depth_and_delete(database, user, config, senses):
    _, sessions, _ = database
    system = await system_roots(sessions, user)
    a = await create(sessions, user, config, type="FOLDER", name="a")
    b = await create(sessions, user, config, type="FOLDER", name="b", parent_id=a["id"])
    deck = await create(
        sessions, user, config, type="DECK", name="deck", parent_id=b["id"], sense_ids=senses
    )
    with pytest.raises(Problem, match="node_cycle"):
        await move_to(sessions, user, a, config, parent_id=b["id"])
    with pytest.raises(Problem, match="node_cycle"):
        await create(
            sessions,
            user,
            config,
            type="REFERENCE",
            name="ancestor",
            parent_id=b["id"],
            reference_id=a["id"],
        )
    limited = config.model_copy(
        update={"library": config.library.model_copy(update={"max_depth": 3})}
    )
    with pytest.raises(Problem, match="node_depth_exceeded"):
        await create(sessions, user, limited, type="FOLDER", name="too deep", parent_id=b["id"])
    b = await move_to(sessions, user, b, config, parent_id=system[NodeRole.PERSONAL_ROOT].id)
    async with sessions() as session:
        assert (
            await session.scalar(
                select(NodePath.depth).where(
                    NodePath.ancestor_id == system[NodeRole.LIBRARY_ROOT].id,
                    NodePath.descendant_id == deck["id"],
                )
            )
            == 3
        )
        assert await session.get(NodePath, (a["id"], deck["id"])) is None
    await move_to(sessions, user, a, config, parent_id=b["id"])
    await delete_node_in(sessions, user, b, config)
    async with sessions() as session:
        with pytest.raises(Problem, match="node_not_found"):
            await readable(session, deck["id"], user.id, config)
        assert (
            await session.scalar(
                select(func.count())
                .select_from(NodePath)
                .where(NodePath.descendant_id == deck["id"])
            )
            == 0
        )


async def delete_node_in(sessions, user, node, config):
    async with sessions() as session:
        await delete_node(session, user.id, node["id"], config)


async def test_indirect_reference_cycles_deduplicate_and_budgets_fail_explicitly(
    database, user, config, senses
):
    _, sessions, _ = database
    a = await create(sessions, user, config, type="FOLDER", name="a")
    b = await create(sessions, user, config, type="FOLDER", name="b")
    for parent, target in ((a, b), (b, a)):
        await create(
            sessions,
            user,
            config,
            type="REFERENCE",
            name="link",
            parent_id=parent["id"],
            reference_id=target["id"],
        )
    for parent in (a, b):
        await create(
            sessions,
            user,
            config,
            type="DECK",
            name="deck",
            parent_id=parent["id"],
            sense_ids=senses,
        )
    budget = ScopeBudget(user.id)
    assert await ids(sessions, a["id"], user.id, config, budget) == set(senses)
    assert len(budget.nodes) == 6 and budget.memberships == 4
    assert await ids(sessions, b["id"], user.id, config, budget) == set(senses)
    assert len(budget.nodes) == 6 and budget.memberships == 4
    for changes in ({"max_scope_nodes": 5}, {"max_scope_memberships": 3}):
        limited = config.model_copy(update={"library": config.library.model_copy(update=changes)})
        with pytest.raises(Problem, match="scope_too_large"):
            await ids(sessions, a["id"], user.id, limited)


async def test_concurrent_opposing_moves_and_child_quota(database, user, config):
    _, sessions, _ = database
    a = await create(sessions, user, config, type="FOLDER", name="a")
    b = await create(sessions, user, config, type="FOLDER", name="b")

    async def move(source, target):
        try:
            await move_to(sessions, user, source, config, parent_id=target["id"])
            return "ok"
        except Problem as exc:
            return exc.code

    assert sorted(await asyncio.gather(move(a, b), move(b, a))) == ["node_cycle", "ok"]
    folder = await create(sessions, user, config, type="FOLDER", name="capacity")
    limited = config.model_copy(
        update={"library": config.library.model_copy(update={"max_children_per_folder": 1})}
    )

    async def child():
        try:
            await create(
                sessions, user, limited, type="FOLDER", name="child", parent_id=folder["id"]
            )
            return "ok"
        except Problem as exc:
            return exc.code

    assert sorted(await asyncio.gather(child(), child())) == ["ok", "quota_exceeded"]


async def test_node_http_contract_paginated_senses_and_safe_profiles(
    resources, user, config, senses
):
    sessions, lexicon = resources.sessions, resources.lexicon
    deck = await create(sessions, user, config, type="DECK", name="deck", sense_ids=senses)
    with pytest.raises(Problem, match="sense_not_found"):
        async with sessions() as session:
            await patch_senses(session, user.id, deck["id"], SenseDelta(add=[99999]), config)
    async with sessions() as session:
        editor = await patch_senses(session, user.id, deck["id"], SenseDelta(), config)
        assert editor["name"] == "deck" and editor["sense_ids"] == senses
    now = datetime.now(UTC)
    async with sessions() as session, session.begin():
        session.add(
            UserSense(
                user_id=user.id,
                sense_id=1,
                stability=5,
                difficulty=5,
                last_exposure_at=now,
                due_at=now - timedelta(seconds=1),
                elo=600,
                review_count=1,
                lapse_count=0,
            )
        )
    limited = config.model_copy(
        update={"library": config.library.model_copy(update={"page_size": 1})}
    )
    async with sessions() as session:
        node = await readable(session, deck["id"], user.id, config)
        first = await sense_page(session, node, user.id, limited, lexicon)
        second = await sense_page(session, node, user.id, limited, lexicon, first["next_cursor"])
        assert [s["sense_id"] for s in first["senses"]] == [1]
        assert [s["sense_id"] for s in second["senses"]] == [2]
        assert first["senses"][0]["learning"]["state"] == "DUE"
        assert "mastery" not in first["senses"][0]["learning"]
        assert (await sense_page(session, node, user.id, limited, lexicon, state="NEW"))["senses"][
            0
        ]["sense_id"] == 2
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
        detail = (await client.get(f"/v1/nodes/{deck['id']}")).json()
        assert "senses" not in detail and "sense_count" not in detail
        assert (
            await client.patch(
                f"/v1/nodes/{deck['id']}",
                json={"name": "deck", "visibility": "PRIVATE", "sense_ids": senses},
            )
        ).status_code == 422
        assert (await client.get("/v1/library/nodes")).status_code == 404
        profile = (await client.get("/v1/me")).json()
        public = (await client.get(f"/v1/users/{user.id}")).json()
        assert public == {
            "id": str(user.id),
            "display_name": user.display_name,
            "handle": user.handle,
            "bio": None,
            "joined_at": profile["joined_at"],
            "published_node_id": profile["published_node_id"],
        }
        assert "personal_node_id" not in public and "settings" not in public


async def test_reference_chain_does_not_consume_physical_depth(database, user, config, senses):
    _, sessions, _ = database
    limited = config.model_copy(
        update={"library": config.library.model_copy(update={"max_depth": 3})}
    )
    folders = [
        await create(sessions, user, limited, type="FOLDER", name=f"folder-{i}") for i in range(25)
    ]
    for source, target in zip(folders, folders[1:], strict=False):
        await create(
            sessions,
            user,
            limited,
            type="REFERENCE",
            name="next",
            parent_id=source["id"],
            reference_id=target["id"],
        )
    await create(
        sessions,
        user,
        limited,
        type="DECK",
        name="deep logical scope",
        parent_id=folders[-1]["id"],
        sense_ids=senses,
    )
    assert await ids(sessions, folders[0]["id"], user.id, limited) == set(senses)


async def test_subtree_move_checks_embedded_reference_targets(database, user, config):
    _, sessions, _ = database
    source = await create(sessions, user, config, type="FOLDER", name="source")
    target = await create(sessions, user, config, type="FOLDER", name="target")
    await create(
        sessions,
        user,
        config,
        type="REFERENCE",
        name="target link",
        parent_id=source["id"],
        reference_id=target["id"],
    )
    with pytest.raises(Problem, match="node_cycle"):
        await move_to(sessions, user, source, config, parent_id=target["id"])


async def test_owned_node_and_membership_quota_races(database, user, config, senses):
    _, sessions, _ = database
    limited = config.model_copy(
        update={"library": config.library.model_copy(update={"max_owned_nodes": 3})}
    )

    async def one_node():
        try:
            await create(sessions, user, limited, type="FOLDER", name="candidate")
            return "ok"
        except Problem as exc:
            return exc.code

    # Personal and Published count; Library alone is excluded.
    assert sorted(await asyncio.gather(one_node(), one_node())) == ["ok", "quota_exceeded"]
    a = await create(sessions, user, config, type="DECK", name="a", sense_ids=[1])
    b = await create(sessions, user, config, type="DECK", name="b", sense_ids=[2])
    limited = config.model_copy(
        update={"library": config.library.model_copy(update={"max_owned_memberships": 3})}
    )

    async def membership(node):
        try:
            async with sessions() as session:
                await patch_senses(session, user.id, node["id"], SenseDelta(add=senses), limited)
            return "ok"
        except Problem as exc:
            return exc.code

    assert sorted(await asyncio.gather(membership(a), membership(b))) == ["ok", "quota_exceeded"]
    # A reduction is legal even if a migrated account already exceeds a quota.
    async with sessions() as session:
        await patch_senses(session, user.id, a["id"], SenseDelta(remove=[1]), limited)


async def test_corrupted_space_never_grants_access_or_skips_publication_consent(
    database, user, config
):
    _, sessions, _ = database
    system = await system_roots(sessions, user)
    private = await create(sessions, user, config, type="FOLDER", name="still private")
    async with sessions() as session, session.begin():
        await session.execute(
            text("UPDATE nodes SET space='PUBLISHED' WHERE id=:id"), {"id": private["id"]}
        )
    async with sessions() as session:
        with pytest.raises(Problem, match="node_not_found"):
            await readable(session, private["id"], None, config)
    with pytest.raises(Problem, match="invalid_tree_space"):
        await move_to(sessions, user, private, config, parent_id=system[NodeRole.PUBLISHED_ROOT].id)


async def test_membership_delta_retains_members_beyond_browse_page(database, user, config, senses):
    engine, sessions, _ = database
    async with engine.begin() as connection:
        await connection.execute(
            text("""
            INSERT INTO lexi.senses(id,word_id,pos,tier)
            SELECT id,1,'NOUN','COMMON' FROM generate_series(3,1001) AS id
        """)
        )
    deck = await create(
        sessions, user, config, type="DECK", name="full", sense_ids=list(range(1, 1001))
    )
    async with sessions() as session:
        assert (
            len(
                (await patch_senses(session, user.id, deck["id"], SenseDelta(), config))[
                    "sense_ids"
                ]
            )
            == 1000
        )
    with pytest.raises(Problem, match="deck_sense_limit_exceeded"):
        async with sessions() as session:
            await patch_senses(session, user.id, deck["id"], SenseDelta(add=[1001]), config)
    async with sessions() as session:
        assert (await session.get(Node, deck["id"])).name == "full"


async def test_targeted_metadata_and_concurrent_membership_preserve_state(
    database, user, config, senses
):
    _, sessions, _ = database
    folder = await create(sessions, user, config, type="FOLDER", name="folder")
    deck = await create(
        sessions, user, config, type="DECK", name="deck", parent_id=folder["id"], sense_ids=senses
    )
    async with sessions() as session:
        await patch_node(session, user.id, deck["id"], NodePatch(description="changed"), config)
    async with sessions() as session:
        snapshot = await patch_senses(session, user.id, deck["id"], SenseDelta(), config)
        assert snapshot["parent_id"] == folder["id"]
        assert snapshot["name"] == "deck" and snapshot["sense_ids"] == senses
    async with sessions() as session:
        await patch_senses(session, user.id, deck["id"], SenseDelta(remove=senses), config)

    async def add(sense_id):
        async with sessions() as session:
            await patch_senses(session, user.id, deck["id"], SenseDelta(add=[sense_id]), config)

    await asyncio.gather(*(add(sense_id) for sense_id in senses))
    async with sessions() as session:
        assert (await patch_senses(session, user.id, deck["id"], SenseDelta(), config))[
            "sense_ids"
        ] == senses
    with pytest.raises(Problem, match="sense_not_found"):
        async with sessions() as session:
            await patch_senses(
                session, user.id, deck["id"], SenseDelta(add=[999999], remove=senses), config
            )
    async with sessions() as session:
        assert (await patch_senses(session, user.id, deck["id"], SenseDelta(), config))[
            "sense_ids"
        ] == senses
    with pytest.raises(Problem, match="membership_is_deck_only"):
        async with sessions() as session:
            await patch_senses(session, user.id, folder["id"], SenseDelta(add=senses), config)
    other = await other_user(sessions)
    with pytest.raises(Problem, match="node_not_found"):
        async with sessions() as session:
            await patch_node(session, other.id, deck["id"], NodePatch(name="stolen"), config)


async def test_targeted_move_publication_preserves_membership_and_reference(
    database, user, config, senses
):
    _, sessions, _ = database
    system = await system_roots(sessions, user)
    deck = await create(sessions, user, config, type="DECK", name="deck", sense_ids=senses)
    with pytest.raises(Problem, match="publication_confirmation_required"):
        async with sessions() as session:
            await move_node(
                session,
                user.id,
                deck["id"],
                NodeMove(parent_id=system[NodeRole.PUBLISHED_ROOT].id),
                config,
            )
    async with sessions() as session:
        moved = await move_node(
            session,
            user.id,
            deck["id"],
            NodeMove(
                parent_id=system[NodeRole.PUBLISHED_ROOT].id,
                confirm_publication=True,
                retain_personal_reference=True,
            ),
            config,
        )
    assert moved["id"] == deck["id"] and moved["retained_reference_id"]
    assert await ids(sessions, deck["id"], None, config) == set(senses)
    async with sessions() as session:
        assert (await patch_senses(session, user.id, deck["id"], SenseDelta(), config))[
            "sense_ids"
        ] == senses
        reference = await node_details(session, moved["retained_reference_id"], user.id, config)
        assert reference["reference_id"] == deck["id"]
    async with sessions() as session:
        await move_node(
            session,
            user.id,
            deck["id"],
            NodeMove(parent_id=system[NodeRole.PERSONAL_ROOT].id),
            config,
        )
    async with sessions() as session:
        with pytest.raises(Problem, match="node_not_found"):
            await readable(session, deck["id"], None, config)


async def test_copy_is_atomic_independent_and_remaps_internal_references(
    database, user, config, senses
):
    _, sessions, _ = database
    system = await system_roots(sessions, user)
    folder = await create(sessions, user, config, type="FOLDER", name="folder")
    nested = await create(
        sessions, user, config, type="FOLDER", name="nested", parent_id=folder["id"]
    )
    deck = await create(
        sessions, user, config, type="DECK", name="deck", parent_id=nested["id"], sense_ids=senses
    )
    await create(
        sessions,
        user,
        config,
        type="REFERENCE",
        name="linked deck",
        parent_id=folder["id"],
        reference_id=deck["id"],
    )
    async with sessions() as session:
        copied = await copy_node(
            session,
            user.id,
            folder["id"],
            NodeDestination(parent_id=system[NodeRole.PERSONAL_ROOT].id),
            config,
        )
    async with sessions() as session:
        children = (await list_nodes(session, user.id, copied["id"], None, config))["nodes"]
    copy_nested = next(node for node in children if node["type"].value == "FOLDER")
    async with sessions() as session:
        copy_deck = (await list_nodes(session, user.id, copy_nested["id"], None, config))["nodes"][
            0
        ]
    copy_ref = next(node for node in children if node["type"].value == "REFERENCE")
    assert copy_deck["id"] != deck["id"] and copy_ref["reference_id"] == copy_deck["id"]
    async with sessions() as session:
        await patch_senses(session, user.id, copy_deck["id"], SenseDelta(remove=senses), config)
    assert await ids(sessions, deck["id"], user.id, config) == set(senses)
    assert await ids(sessions, copied["id"], user.id, config) == set()
    with pytest.raises(Problem, match="publication_confirmation_required"):
        async with sessions() as session:
            await copy_node(
                session,
                user.id,
                folder["id"],
                NodeDestination(parent_id=system[NodeRole.PUBLISHED_ROOT].id),
                config,
            )
    async with sessions() as session:
        assert (await list_nodes(session, None, system[NodeRole.PUBLISHED_ROOT].id, None, config))[
            "nodes"
        ] == []
    async with sessions() as session:
        published = await copy_node(
            session,
            user.id,
            folder["id"],
            NodeDestination(parent_id=system[NodeRole.PUBLISHED_ROOT].id, confirm_publication=True),
            config,
        )
    assert await ids(sessions, published["id"], None, config) == set(senses)
    with pytest.raises(Problem, match="node_cycle"):
        async with sessions() as session:
            await copy_node(
                session, user.id, folder["id"], NodeDestination(parent_id=folder["id"]), config
            )


async def test_targeted_routes_http_contract(resources, user, config, senses):
    sessions = resources.sessions
    deck = await create(sessions, user, config, type="DECK", name="deck", sense_ids=senses)
    system = await system_roots(sessions, user)
    app = create_app()
    for name, value in vars(resources).items():
        setattr(app.state, name, value)
    app.state.product = config

    async def authenticated():
        return user

    app.dependency_overrides[actor] = authenticated
    app.dependency_overrides[optional_actor] = authenticated
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        assert (
            await client.patch(f"/v1/nodes/{deck['id']}", json={"name": "renamed"})
        ).status_code == 200
        changed = await client.post(
            f"/v1/nodes/{deck['id']}:modifySenses", json={"add": [], "remove": [senses[0]]}
        )
        assert changed.status_code == 200 and changed.json()["sense_ids"] == senses[1:]
        copied = await client.post(
            f"/v1/nodes/{deck['id']}:copy",
            json={"parent_id": str(system[NodeRole.PERSONAL_ROOT].id)},
        )
        assert copied.status_code == 201 and copied.json()["sense_ids"] == senses[1:]
        moved = await client.post(
            f"/v1/nodes/{deck['id']}:move",
            json={
                "parent_id": str(system[NodeRole.PUBLISHED_ROOT].id),
                "confirm_publication": True,
            },
        )
        assert moved.status_code == 200 and moved.json()["id"] == str(deck["id"])
        page = (await client.get(f"/v1/nodes/{deck['id']}/senses")).json()
        assert [item["sense_id"] for item in page["senses"]] == senses[1:]


async def test_http_child_and_sense_quotas_reject_atomically(resources, user, config, senses):
    limited = config.model_copy(
        update={
            "library": config.library.model_copy(
                update={"max_children_per_folder": 2, "max_senses_per_deck": 2}
            )
        }
    )
    parent = await create(resources.sessions, user, limited, type="FOLDER", name="parent")
    await create(
        resources.sessions, user, limited, type="DECK", name="existing", parent_id=parent["id"]
    )
    deck = await create(
        resources.sessions, user, limited, type="DECK", name="members", sense_ids=[senses[0]]
    )
    app = create_app()
    for name, value in vars(resources).items():
        setattr(app.state, name, value)
    app.state.product = limited

    async def authenticated():
        return user

    app.dependency_overrides[actor] = authenticated
    app.dependency_overrides[optional_actor] = authenticated
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        writes = await asyncio.gather(
            *(
                client.post(
                    "/v1/nodes",
                    json={
                        "type": "DECK",
                        "name": f"candidate-{i}",
                        "parent_id": str(parent["id"]),
                        "sense_ids": [],
                    },
                )
                for i in range(2)
            )
        )
        assert sorted(response.status_code for response in writes) == [201, 422]
        assert next(response for response in writes if response.status_code == 422).json() == {
            "error": "quota_exceeded"
        }
        denied = await client.post(
            f"/v1/nodes/{deck['id']}:modifySenses",
            json={"add": [senses[0], senses[1], 2147483647], "remove": []},
        )
        assert denied.status_code == 422
        assert denied.json() == {"error": "deck_sense_limit_exceeded"}
        members = await client.get(f"/v1/nodes/{deck['id']}/senses")
        assert [sense["sense_id"] for sense in members.json()["senses"]] == [senses[0]]
        children = await client.get("/v1/nodes", params={"parent_id": str(parent["id"])})
        assert len(children.json()["nodes"]) == 2


async def test_http_owned_quota_races_copy_and_deletion_release_one_slot(resources, user, config):
    limited = config.model_copy(
        update={
            "library": config.library.model_copy(
                update={"max_owned_nodes": 5, "max_children_per_folder": 3}
            )
        }
    )
    parent = await create(resources.sessions, user, limited, type="FOLDER", name="parent")
    deck = await create(
        resources.sessions, user, limited, type="DECK", name="existing", parent_id=parent["id"]
    )
    app = create_app()
    for name, value in vars(resources).items():
        setattr(app.state, name, value)
    app.state.product = limited

    async def authenticated():
        return user

    app.dependency_overrides[actor] = authenticated
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        writes = await asyncio.gather(
            *(
                client.post(
                    "/v1/nodes",
                    json={
                        "type": "DECK",
                        "name": f"candidate-{i}",
                        "parent_id": str(parent["id"]),
                        "sense_ids": [],
                    },
                )
                for i in range(2)
            )
        )
        assert sorted(response.status_code for response in writes) == [201, 422]
        assert next(response for response in writes if response.status_code == 422).json() == {
            "error": "quota_exceeded"
        }
        copy = await client.post(
            f"/v1/nodes/{deck['id']}:copy", json={"parent_id": str(parent["id"])}
        )
        assert copy.status_code == 422 and copy.json() == {"error": "quota_exceeded"}
        assert (await client.delete(f"/v1/nodes/{deck['id']}")).status_code == 204
        replacement = await client.post(
            "/v1/nodes",
            json={
                "type": "DECK",
                "name": "replacement",
                "parent_id": str(parent["id"]),
                "sense_ids": [],
            },
        )
        assert replacement.status_code == 201 and replacement.json()["id"] != str(deck["id"])
        full = await client.post(
            "/v1/nodes",
            json={
                "type": "DECK",
                "name": "still full",
                "parent_id": str(parent["id"]),
                "sense_ids": [],
            },
        )
        assert full.status_code == 422 and full.json() == {"error": "quota_exceeded"}
