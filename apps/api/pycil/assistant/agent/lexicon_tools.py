"""Actor-aware content operations for assistant tools."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.lexicon.provider import get_lexi_client
from pycil.library import membership
from pycil.library.access import ActorRef, require_node_access
from pycil.library.models import DeckSense, Node, NodeType
from pycil.platform.errors import ConflictError, NotFoundError


async def _require_deck(session: AsyncSession, actor_id: UUID, deck_id: UUID) -> Node:
    """Resolve a tool-supplied deck id through the canonical ownership gate."""
    deck = await require_node_access(session, deck_id, ActorRef(actor_id), write=True)
    if deck.type != NodeType.DECK:
        raise ConflictError("deck_senses_require_deck")
    return deck


async def list_deck_items(
    session: AsyncSession, actor_id: UUID, deck_id: UUID, limit: int, cursor: int | None = None
) -> dict:
    await _require_deck(session, actor_id, deck_id)
    query = select(DeckSense).where(DeckSense.node_id == deck_id)
    if cursor is not None:
        cursor_row = await session.get(DeckSense, cursor)
        if cursor_row is None or cursor_row.node_id != deck_id:
            raise NotFoundError("assistant_cursor_not_in_collection")
        query = query.where(DeckSense.id > cursor)
    rows = list(await session.scalars(query.order_by(DeckSense.id).limit(limit + 1)))
    page, extra = rows[:limit], rows[limit:]
    views = await membership.resolve_senses(get_lexi_client(), [row.sense_id for row in page])
    return {
        "items": [
            {
                "sense_id": view.sense_id,
                "definition": view.definition,
                "cefr_level": view.cefr_level,
            }
            for view in views
        ],
        "next_cursor": page[-1].id if extra and page else None,
    }


async def add_senses(
    session: AsyncSession, actor_id: UUID, deck_id: UUID, sense_ids: list[int]
) -> dict:
    """Add many senses in one authorized, one-transaction call."""
    await _require_deck(session, actor_id, deck_id)
    rows = await membership.add_senses(session, deck_id, sense_ids)
    return {
        "requested": len(sense_ids),
        "added": len(rows),
        "sense_ids": [row.sense_id for row in rows],
    }


async def remove_senses(
    session: AsyncSession,
    actor_id: UUID,
    deck_id: UUID,
    sense_ids: list[int],
    *,
    commit: bool = True,
) -> dict:
    """Remove many senses in one authorized, one-transaction call."""
    await _require_deck(session, actor_id, deck_id)
    removed = await membership.remove_senses(session, deck_id, sense_ids, commit=commit)
    return {"requested": len(sense_ids), "removed": removed}
