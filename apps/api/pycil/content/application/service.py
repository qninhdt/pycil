"""Content service: deck membership only.

pycil records only ``deck_senses`` membership (opaque sense_id). Sense content
for display is resolved through the LexiReader port, never stored.
"""

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.common.errors import ConflictError, NotFoundError
from pycil.content.infra.models import DeckSense
from pycil.hierarchy.application import cache
from pycil.hierarchy.application import service as hierarchy_service
from pycil.hierarchy.infra.models import Node, NodeType
from pycil.policy.sense_state import UserSenseStats
from pycil.ports.lexi import LexiReader


async def create_deck(
    session: AsyncSession,
    author_id: UUID,
    name: str,
    parent_node_id: UUID | None = None,
) -> Node:
    """Create a DECK node + its attributes row."""
    return await hierarchy_service.create_node(
        session,
        author_id,
        node_type=NodeType.DECK,
        name=name,
        parent_node_id=parent_node_id,
    )


async def add_sense(session: AsyncSession, node_id: UUID, sense_id: int) -> DeckSense:
    """Append a sense to a deck (idempotent on the UNIQUE(node_id, sense_id))."""
    await _require_live_deck(session, node_id)
    existing = await session.execute(
        select(DeckSense).where(DeckSense.node_id == node_id, DeckSense.sense_id == sense_id)
    )
    row = existing.scalars().first()
    if row is not None:
        return row
    next_pos = await _next_position(session, node_id)
    row = DeckSense(node_id=node_id, sense_id=sense_id, position=next_pos)
    session.add(row)
    await cache.bump_deck_content_generation(session, node_id)
    await session.commit()
    await session.refresh(row)
    return row


async def add_senses(session: AsyncSession, node_id: UUID, sense_ids: list[int]) -> list[DeckSense]:
    """Append many senses in ONE transaction.

    A deck edit that named five words is one user action, so it commits once: N
    separate commits would leave a half-applied deck if the fourth failed, and
    would bump the deck's content generation N times for one edit.
    """
    await _require_live_deck(session, node_id)
    if not sense_ids:
        return []
    present = set(
        (
            await session.execute(
                select(DeckSense.sense_id).where(
                    DeckSense.node_id == node_id, DeckSense.sense_id.in_(sense_ids)
                )
            )
        ).scalars()
    )
    position = await _next_position(session, node_id)
    added: list[DeckSense] = []
    seen: set[int] = set()
    for sense_id in sense_ids:
        # A duplicate in the request is the same membership as the first, so it
        # is skipped rather than rejected: the caller asked for a final state,
        # not for an error about how they wrote it.
        if sense_id in present or sense_id in seen:
            continue
        seen.add(sense_id)
        row = DeckSense(node_id=node_id, sense_id=sense_id, position=position)
        position += 1
        session.add(row)
        added.append(row)
    if added:
        await cache.bump_deck_content_generation(session, node_id)
    await session.commit()
    for row in added:
        await session.refresh(row)
    return added


async def remove_senses(
    session: AsyncSession, node_id: UUID, sense_ids: list[int], *, commit: bool = True
) -> int:
    """Remove many senses in ONE transaction, returning how many rows were deleted."""
    await _require_live_deck(session, node_id)
    if not sense_ids:
        return 0
    result = await session.execute(
        delete(DeckSense).where(
            DeckSense.node_id == node_id, DeckSense.sense_id.in_(set(sense_ids))
        )
    )
    removed = result.rowcount or 0
    if removed:
        await cache.bump_deck_content_generation(session, node_id)
    if commit:
        await session.commit()
    else:
        await session.flush()
    return removed


async def remove_sense(
    session: AsyncSession, node_id: UUID, sense_id: int, *, commit: bool = True
) -> None:
    await remove_senses(session, node_id, [sense_id], commit=commit)



async def list_sense_ids(session: AsyncSession, node_id: UUID) -> list[int]:
    result = await session.execute(
        select(DeckSense.sense_id)
        .where(DeckSense.node_id == node_id)
        .order_by(DeckSense.position, DeckSense.id)
    )
    return [row[0] for row in result]


async def learning_state_for(
    session: AsyncSession, user_id: UUID | None, sense_ids: list[int]
) -> dict[int, UserSenseStats]:
    """The caller's stats for these senses, in ONE query for the whole deck.

    Empty for an anonymous caller: learning state is per-user, and there is no
    sensible default to invent. A sense with no row is absent from the mapping
    rather than present-and-zero, so the caller can tell "never studied" from
    "studied and scored zero".
    """
    if user_id is None or not sense_ids:
        return {}
    rows = await session.execute(
        select(UserSenseStats).where(
            UserSenseStats.user_id == user_id,
            UserSenseStats.sense_id.in_(sense_ids),
        )
    )
    return {row.sense_id: row for row in rows.scalars()}


async def deck_ids_for_sense(session: AsyncSession, sense_id: int) -> list[UUID]:
    """Every deck holding this sense, unauthorized.

    The caller MUST narrow this through ``subtree.readable_deck_ids`` before
    exposing anything: membership alone says nothing about who may read it.
    """
    result = await session.execute(
        select(DeckSense.node_id).where(DeckSense.sense_id == sense_id).distinct()
    )
    return [row[0] for row in result]


async def resolve_senses(client: LexiReader, sense_ids: list[int]) -> list:
    """Resolve sense content for display through the port (never from pycil DB)."""
    if not sense_ids:
        return []
    return await client.get_senses(sense_ids)


async def _next_position(session: AsyncSession, node_id: UUID) -> int:
    result = await session.execute(
        select(func.coalesce(func.max(DeckSense.position), -1)).where(DeckSense.node_id == node_id)
    )
    return int(result.scalar_one()) + 1


async def _require_live_deck(session: AsyncSession, node_id: UUID) -> Node:
    node = await session.get(Node, node_id, with_for_update=True)
    if node is None or node.deleted_at is not None:
        raise NotFoundError("deck_not_found")
    if node.type != NodeType.DECK:
        raise ConflictError("deck_senses_require_deck")
    return node

