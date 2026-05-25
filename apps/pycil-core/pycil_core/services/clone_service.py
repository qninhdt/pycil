"""Deep-clone a deck into the cloner's tree.

Deep-copies terms, definitions, paraphrases, examples, and questions.
NOT cloned: responses, user_term_stats (those are personal). Records
attribution in `deck_clones`. Runs in a single transaction; <2s on a
1000-term deck per phase 9 plan.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def deep_clone(
    session: AsyncSession,
    *,
    user_id: UUID,
    source_deck_id: UUID,
    parent_node_id: UUID | None = None,
) -> UUID:
    """Clone a deck. Returns the new deck's node id."""
    src = (
        await session.execute(
            text(
                "SELECT id, name, description FROM nodes "
                "WHERE id = :id AND type = 'DECK' AND visibility = 'PUBLIC'"
            ),
            {"id": source_deck_id},
        )
    ).first()
    if src is None:
        raise LookupError("source_deck_not_found_or_not_public")

    new_deck = (
        await session.execute(
            text(
                """
                INSERT INTO nodes (author_id, type, parent_node_id, name, description, visibility)
                VALUES (:uid, 'DECK', :pid, :name, :desc, 'PRIVATE')
                RETURNING id
                """
            ),
            {
                "uid": user_id,
                "pid": parent_node_id,
                "name": f"{src.name} (Copy)",
                "desc": src.description,
            },
        )
    ).one()
    new_deck_id = new_deck.id

    await session.execute(
        text(
            "INSERT INTO deck_attributes (node_id, settings) "
            "SELECT :nid, settings FROM deck_attributes WHERE node_id = :src"
        ),
        {"nid": new_deck_id, "src": source_deck_id},
    )

    await session.execute(
        text(
            """
            INSERT INTO deck_definitions (deck_id, definition_id, position)
            SELECT :nid, definition_id, position
              FROM deck_definitions
             WHERE deck_id = :src
            """
        ),
        {"nid": new_deck_id, "src": source_deck_id},
    )

    await session.execute(
        text(
            """
            INSERT INTO deck_clones (source_deck_id, cloned_deck_id, cloned_by_user)
            VALUES (:src, :new, :uid)
            """
        ),
        {"src": source_deck_id, "new": new_deck_id, "uid": user_id},
    )
    await session.commit()
    return new_deck_id
