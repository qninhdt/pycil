"""Actor-aware content operations for assistant tools."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.assistant.application.hierarchy_facade import _owned_node
from pycil.common.errors import ConflictError, NotFoundError
from pycil.content.application import service
from pycil.content.infra.models import DeckSense
from pycil.hierarchy.infra.models import NodeType
from pycil.ports.lexi_provider import get_lexi_client


async def _owned_deck(session: AsyncSession, actor_id: UUID, deck_id: UUID):
    deck = await _owned_node(session, actor_id, deck_id)
    if deck.type != NodeType.DECK:
        raise ConflictError("deck_senses_require_deck")
    return deck


async def list_deck_items(
    session: AsyncSession, actor_id: UUID, deck_id: UUID, limit: int, cursor: int | None = None
) -> dict:
    await _owned_deck(session, actor_id, deck_id)
    query = select(DeckSense).where(DeckSense.node_id == deck_id)
    if cursor is not None:
        cursor_row = await session.get(DeckSense, cursor)
        if cursor_row is None or cursor_row.node_id != deck_id:
            raise NotFoundError("assistant_cursor_not_in_collection")
        query = query.where(DeckSense.id > cursor)
    rows = list(await session.scalars(query.order_by(DeckSense.id).limit(limit + 1)))
    page, extra = rows[:limit], rows[limit:]
    views = await service.resolve_senses(get_lexi_client(), [row.sense_id for row in page])
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


async def add_sense(session: AsyncSession, actor_id: UUID, deck_id: UUID, sense_id: int) -> dict:
    await _owned_deck(session, actor_id, deck_id)
    row = await service.add_sense(session, deck_id, sense_id)
    return {"id": row.id, "sense_id": row.sense_id}


async def remove_sense(
    session: AsyncSession, actor_id: UUID, deck_id: UUID, sense_id: int, *, commit: bool = True
) -> None:
    await _owned_deck(session, actor_id, deck_id)
    await service.remove_sense(session, deck_id, sense_id, commit=commit)
