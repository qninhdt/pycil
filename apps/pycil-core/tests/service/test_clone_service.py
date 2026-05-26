"""Clone service: deep-copy invariants, public-only enforcement.

Pins:
- private source → LookupError
- foreign parent_node_id → LookupError
- empty deck clones cleanly
- terms.value UNIQUE → ON CONFLICT path reuses existing row
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from pycil_core.services import clone_service
from tests.factories import (
    attach_definition_to_deck,
    make_deck,
    make_definition,
    make_term,
)


async def test_deep_clone_rejects_private_source(session, test_user, second_user) -> None:
    src = await make_deck(session, author_id=second_user["id"], visibility="PRIVATE")

    with pytest.raises(LookupError, match="source_deck_not_found_or_not_public"):
        await clone_service.deep_clone(
            session, user_id=test_user["id"], source_deck_id=src["id"]
        )


async def test_deep_clone_rejects_foreign_parent(session, test_user, second_user) -> None:
    src = await make_deck(session, author_id=second_user["id"], visibility="PUBLIC")

    # Folder owned by a third user (or the source author, not the cloner).
    folder_row = (
        await session.execute(
            text(
                "INSERT INTO nodes (author_id, type, name) "
                "VALUES (:aid, 'FOLDER', 'theirs') RETURNING id"
            ),
            {"aid": second_user["id"]},
        )
    ).one()
    await session.commit()

    with pytest.raises(LookupError, match="parent_folder_not_found_or_not_owned"):
        await clone_service.deep_clone(
            session,
            user_id=test_user["id"],
            source_deck_id=src["id"],
            parent_node_id=folder_row.id,
        )


async def test_deep_clone_empty_deck(session, test_user, second_user) -> None:
    src = await make_deck(session, author_id=second_user["id"], visibility="PUBLIC")

    new_deck_id = await clone_service.deep_clone(
        session, user_id=test_user["id"], source_deck_id=src["id"]
    )
    assert new_deck_id is not None

    # New deck owned by cloner, PRIVATE visibility, name suffixed.
    row = (
        await session.execute(
            text(
                "SELECT author_id, visibility::text AS v, name "
                "FROM nodes WHERE id = :id"
            ),
            {"id": new_deck_id},
        )
    ).one()
    assert row.author_id == test_user["id"]
    assert row.v == "PRIVATE"
    assert row.name.endswith("(Copy)")

    # Zero deck_definitions for empty source.
    count = (
        await session.execute(
            text("SELECT COUNT(*) AS c FROM deck_definitions WHERE deck_id = :id"),
            {"id": new_deck_id},
        )
    ).one().c
    assert count == 0


async def test_deep_clone_reuses_existing_term(session, test_user, second_user) -> None:
    """Terms.value is UNIQUE — second clone of the same term value via a
    different cloner/source must not duplicate the term row."""
    # Build source deck with one term/definition.
    src = await make_deck(session, author_id=second_user["id"], visibility="PUBLIC")
    term_id = await make_term(session, value="hello-world-term")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=src["id"], definition_id=def_id)

    new_deck_id = await clone_service.deep_clone(
        session, user_id=test_user["id"], source_deck_id=src["id"]
    )

    term_count = (
        await session.execute(
            text("SELECT COUNT(*) AS c FROM terms WHERE value = :v"),
            {"v": "hello-world-term"},
        )
    ).one().c
    assert term_count == 1

    # The new deck has exactly 1 deck_definitions row.
    new_dds = (
        await session.execute(
            text("SELECT COUNT(*) AS c FROM deck_definitions WHERE deck_id = :id"),
            {"id": new_deck_id},
        )
    ).one().c
    assert new_dds == 1


async def test_deep_clone_records_attribution(session, test_user, second_user) -> None:
    src = await make_deck(session, author_id=second_user["id"], visibility="PUBLIC")
    new_deck_id = await clone_service.deep_clone(
        session, user_id=test_user["id"], source_deck_id=src["id"]
    )

    row = (
        await session.execute(
            text(
                "SELECT source_deck_id, cloned_deck_id, cloned_by_user "
                "FROM deck_clones WHERE cloned_deck_id = :id"
            ),
            {"id": new_deck_id},
        )
    ).first()
    assert row is not None
    assert row.source_deck_id == src["id"]
    assert row.cloned_by_user == test_user["id"]
