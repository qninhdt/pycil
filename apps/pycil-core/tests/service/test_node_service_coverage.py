"""Node service coverage: CRUD, owner-scoping, breadcrumb, flag toggles.

Pins:
- root + children listing (owner-scoped, foreign owner excluded)
- _ensure_owner 404 / 403 branches
- create folder + deck, parent-must-be-folder rejection, subfolder_count bump
- get_node breadcrumb chain + star/pin reflection
- update_node (name/desc + empty no-op short-circuit)
- delete_node (hard) vs admin_soft_delete_node (reversible, idempotent)
- toggle_flag insert + ON CONFLICT flip, invalid-flag rejection
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from pycil_core.schemas.node import NodeCreate, NodeType, NodeUpdate
from pycil_core.services import node_service
from tests.factories import make_deck


async def _folder_id(session, author_id, name="folder", parent=None):
    row = (
        await session.execute(
            text(
                "INSERT INTO nodes (author_id, type, parent_node_id, name) "
                "VALUES (:aid, 'FOLDER', :pid, :n) RETURNING id"
            ),
            {"aid": author_id, "pid": parent, "n": name},
        )
    ).one()
    await session.execute(
        text("INSERT INTO folder_attributes (node_id) VALUES (:nid)"),
        {"nid": row.id},
    )
    await session.commit()
    return row.id


# --------------------------------------------------------------------------- #
# list_root_nodes / list_children
# --------------------------------------------------------------------------- #

async def test_list_root_nodes_owner_scoped(session, test_user, second_user) -> None:
    mine = await make_deck(session, author_id=test_user["id"], name="mine")
    await make_deck(session, author_id=second_user["id"], name="theirs")

    rows = await node_service.list_root_nodes(session, test_user["id"])
    ids = {str(r.id) for r in rows}
    assert str(mine["id"]) in ids
    assert len(rows) == 1  # foreign deck excluded


async def test_list_root_nodes_excludes_children(session, test_user) -> None:
    folder = await _folder_id(session, test_user["id"])
    child = await make_deck(
        session, author_id=test_user["id"], name="child", parent_node_id=folder
    )
    rows = await node_service.list_root_nodes(session, test_user["id"])
    ids = {str(r.id) for r in rows}
    assert str(folder) in ids
    assert str(child["id"]) not in ids  # has a parent → not root


async def test_list_children_returns_only_children(session, test_user) -> None:
    folder = await _folder_id(session, test_user["id"])
    child = await make_deck(
        session, author_id=test_user["id"], name="child", parent_node_id=folder
    )
    rows = await node_service.list_children(session, test_user["id"], folder)
    assert [str(r.id) for r in rows] == [str(child["id"])]


async def test_list_children_foreign_parent_403(session, test_user, second_user) -> None:
    folder = await _folder_id(session, second_user["id"])
    with pytest.raises(HTTPException) as exc:
        await node_service.list_children(session, test_user["id"], folder)
    assert exc.value.status_code == 403


# --------------------------------------------------------------------------- #
# _ensure_owner branches (via get_node)
# --------------------------------------------------------------------------- #

async def test_get_node_not_found_404(session, test_user) -> None:
    with pytest.raises(HTTPException) as exc:
        await node_service.get_node(session, test_user["id"], uuid4())
    assert exc.value.status_code == 404
    assert exc.value.detail == "node_not_found"


async def test_get_node_forbidden_403(session, test_user, second_user) -> None:
    deck = await make_deck(session, author_id=second_user["id"])
    with pytest.raises(HTTPException) as exc:
        await node_service.get_node(session, test_user["id"], deck["id"])
    assert exc.value.status_code == 403
    assert exc.value.detail == "node_forbidden"


# --------------------------------------------------------------------------- #
# create_node
# --------------------------------------------------------------------------- #

async def test_create_deck_root(session, test_user) -> None:
    out = await node_service.create_node(
        session,
        test_user["id"],
        NodeCreate(type=NodeType.DECK, name="New Deck", description="d"),
    )
    assert out.type == NodeType.DECK
    assert out.name == "New Deck"
    assert out.parent_node_id is None
    # DeckAttribute row created.
    cnt = (
        await session.execute(
            text("SELECT COUNT(*) AS c FROM deck_attributes WHERE node_id = :id"),
            {"id": out.id},
        )
    ).one().c
    assert cnt == 1


async def test_create_folder_under_folder_bumps_subfolder_count(
    session, test_user
) -> None:
    parent = await _folder_id(session, test_user["id"], name="parent")
    out = await node_service.create_node(
        session,
        test_user["id"],
        NodeCreate(type=NodeType.FOLDER, name="sub", parent_node_id=parent),
    )
    assert out.type == NodeType.FOLDER
    assert out.parent_node_id == parent
    sub = (
        await session.execute(
            text("SELECT subfolder_count FROM folder_attributes WHERE node_id = :id"),
            {"id": parent},
        )
    ).one().subfolder_count
    assert sub == 1


async def test_create_node_under_deck_parent_400(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    with pytest.raises(HTTPException) as exc:
        await node_service.create_node(
            session,
            test_user["id"],
            NodeCreate(type=NodeType.DECK, name="x", parent_node_id=deck["id"]),
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "parent_must_be_folder"


async def test_create_node_foreign_parent_403(session, test_user, second_user) -> None:
    parent = await _folder_id(session, second_user["id"])
    with pytest.raises(HTTPException) as exc:
        await node_service.create_node(
            session,
            test_user["id"],
            NodeCreate(type=NodeType.DECK, name="x", parent_node_id=parent),
        )
    assert exc.value.status_code == 403


# --------------------------------------------------------------------------- #
# SHORTCUT nodes (point at an existing owned node via target_node_id)
# --------------------------------------------------------------------------- #

async def test_create_shortcut_persists_target_and_no_attribute(
    session, test_user
) -> None:
    target = await make_deck(session, author_id=test_user["id"], name="target")
    out = await node_service.create_node(
        session,
        test_user["id"],
        NodeCreate(
            type=NodeType.SHORTCUT, name="link", target_node_id=target["id"]
        ),
    )
    assert out.type == NodeType.SHORTCUT
    assert out.target_node_id == target["id"]
    # A SHORTCUT is a pure pointer row — no folder/deck attribute.
    for table in ("folder_attributes", "deck_attributes"):
        cnt = (
            await session.execute(
                text(f"SELECT COUNT(*) AS c FROM {table} WHERE node_id = :id"),
                {"id": out.id},
            )
        ).one().c
        assert cnt == 0


async def test_create_shortcut_to_foreign_node_403(
    session, test_user, second_user
) -> None:
    """A shortcut must not grant access to a node the user cannot already see."""
    foreign = await make_deck(session, author_id=second_user["id"])
    with pytest.raises(HTTPException) as exc:
        await node_service.create_node(
            session,
            test_user["id"],
            NodeCreate(
                type=NodeType.SHORTCUT, name="sneak", target_node_id=foreign["id"]
            ),
        )
    assert exc.value.status_code == 403


async def test_create_shortcut_to_missing_node_404(session, test_user) -> None:
    with pytest.raises(HTTPException) as exc:
        await node_service.create_node(
            session,
            test_user["id"],
            NodeCreate(
                type=NodeType.SHORTCUT, name="dangling", target_node_id=uuid4()
            ),
        )
    assert exc.value.status_code == 404


def test_shortcut_create_requires_target() -> None:
    """DTO validator rejects a SHORTCUT with no target before the service runs."""
    with pytest.raises(ValueError, match="target_node_id is required"):
        NodeCreate(type=NodeType.SHORTCUT, name="no-target")


def test_non_shortcut_rejects_target() -> None:
    with pytest.raises(ValueError, match="only valid for SHORTCUT"):
        NodeCreate(type=NodeType.DECK, name="deck", target_node_id=uuid4())


# --------------------------------------------------------------------------- #
# get_node breadcrumb + star/pin reflection
# --------------------------------------------------------------------------- #

async def test_get_node_breadcrumb_chain(session, test_user) -> None:
    root = await _folder_id(session, test_user["id"], name="root")
    mid = await _folder_id(session, test_user["id"], name="mid", parent=root)
    deck = await make_deck(
        session, author_id=test_user["id"], name="leaf", parent_node_id=mid
    )
    out = await node_service.get_node(session, test_user["id"], deck["id"])
    names = [b.name for b in out.breadcrumb]
    # Ordered root..leaf (depth DESC) — ancestors precede the node itself.
    assert names == ["root", "mid", "leaf"]
    assert out.is_starred is False
    assert out.is_pinned is False


# --------------------------------------------------------------------------- #
# update_node
# --------------------------------------------------------------------------- #

async def test_update_node_changes_name_and_description(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"], name="old")
    out = await node_service.update_node(
        session,
        test_user["id"],
        deck["id"],
        NodeUpdate(name="renamed", description="desc"),
    )
    assert out.name == "renamed"
    assert out.description == "desc"


async def test_update_node_empty_payload_noop(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"], name="keep")
    out = await node_service.update_node(
        session, test_user["id"], deck["id"], NodeUpdate()
    )
    assert out.name == "keep"  # short-circuits, returns current node


# --------------------------------------------------------------------------- #
# delete_node (hard) + admin_soft_delete_node (reversible)
# --------------------------------------------------------------------------- #

async def test_delete_node_hard_removes_row(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    await node_service.delete_node(session, test_user["id"], deck["id"])
    cnt = (
        await session.execute(
            text("SELECT COUNT(*) AS c FROM nodes WHERE id = :id"),
            {"id": deck["id"]},
        )
    ).one().c
    assert cnt == 0


async def test_delete_node_foreign_403(session, test_user, second_user) -> None:
    deck = await make_deck(session, author_id=second_user["id"])
    with pytest.raises(HTTPException) as exc:
        await node_service.delete_node(session, test_user["id"], deck["id"])
    assert exc.value.status_code == 403


async def test_admin_soft_delete_sets_deleted_at(session, second_user) -> None:
    deck = await make_deck(session, author_id=second_user["id"])
    # No owner check — admin acts on a foreign node.
    ok = await node_service.admin_soft_delete_node(session, deck["id"])
    await session.commit()
    assert ok is True
    row = (
        await session.execute(
            text("SELECT deleted_at FROM nodes WHERE id = :id"),
            {"id": deck["id"]},
        )
    ).one()
    assert row.deleted_at is not None


async def test_admin_soft_delete_idempotent(session, second_user) -> None:
    deck = await make_deck(session, author_id=second_user["id"])
    first = await node_service.admin_soft_delete_node(session, deck["id"])
    await session.commit()
    second = await node_service.admin_soft_delete_node(session, deck["id"])
    await session.commit()
    assert first is True
    assert second is False  # already soft-deleted → no row updated


async def test_admin_soft_delete_missing_node_false(session) -> None:
    assert await node_service.admin_soft_delete_node(session, uuid4()) is False


# --------------------------------------------------------------------------- #
# toggle_flag
# --------------------------------------------------------------------------- #

async def test_toggle_flag_invalid_field_400(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    with pytest.raises(HTTPException) as exc:
        await node_service.toggle_flag(
            session, test_user["id"], deck["id"], field="bogus"
        )
    assert exc.value.status_code == 400


async def test_toggle_flag_star_insert_then_flip(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    # First toggle → inserts user_nodes row with is_starred TRUE.
    out1 = await node_service.toggle_flag(
        session, test_user["id"], deck["id"], field="is_starred"
    )
    assert out1.is_starred is True
    # Second toggle → ON CONFLICT flips back to FALSE.
    out2 = await node_service.toggle_flag(
        session, test_user["id"], deck["id"], field="is_starred"
    )
    assert out2.is_starred is False


async def test_toggle_flag_pin_independent_of_star(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    await node_service.toggle_flag(
        session, test_user["id"], deck["id"], field="is_starred"
    )
    out = await node_service.toggle_flag(
        session, test_user["id"], deck["id"], field="is_pinned"
    )
    assert out.is_pinned is True
    assert out.is_starred is True  # star untouched by pin toggle
