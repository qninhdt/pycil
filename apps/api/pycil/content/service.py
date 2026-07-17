"""Content service: deck membership + trigger word generation.

pycil records only ``deck_senses`` membership (opaque sense_id). Word generation
is async — enqueued to the worker, which is the single writer to lexi-ai's DB.
Sense content for display is resolved through the LexiClient port, never stored.
"""

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.content.lexi_port import LexiClient
from pycil.content.models import DeckSense
from pycil.hierarchy import cache
from pycil.hierarchy import service as hierarchy_service
from pycil.hierarchy.models import Node, NodeType


async def request_word(arq_pool, user_id: UUID, query: str) -> None:
    """Enqueue lazy generation. The worker is the single writer to lexi's DB."""
    await arq_pool.enqueue_job("generate_word", str(user_id), query)


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


async def rename_deck(session: AsyncSession, node: Node, name: str) -> Node:
    node.name = name
    await session.commit()
    await session.refresh(node)
    return node


async def delete_deck(session: AsyncSession, node: Node) -> None:
    """Soft-delete a deck node."""
    await hierarchy_service.soft_delete_node(session, node)


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
    prior = await cache.bump_generations(session, [node_id])
    await session.commit()
    await session.refresh(row)
    await _delete_prior_defsets(prior)
    return row


async def remove_sense(
    session: AsyncSession, node_id: UUID, sense_id: int, *, commit: bool = True
) -> None:
    await _require_live_deck(session, node_id)
    await session.execute(
        delete(DeckSense).where(DeckSense.node_id == node_id, DeckSense.sense_id == sense_id)
    )
    prior = await cache.bump_generations(session, [node_id])
    if commit:
        await session.commit()
        await _delete_prior_defsets(prior)
    else:
        await session.flush()


async def list_sense_ids(session: AsyncSession, node_id: UUID) -> list[int]:
    result = await session.execute(
        select(DeckSense.sense_id)
        .where(DeckSense.node_id == node_id)
        .order_by(DeckSense.position, DeckSense.id)
    )
    return [row[0] for row in result]


async def resolve_senses(client: LexiClient, sense_ids: list[int]) -> list:
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
        from pycil.common.errors import NotFoundError

        raise NotFoundError("deck_not_found")
    if node.type != NodeType.DECK:
        from pycil.common.errors import ConflictError

        raise ConflictError("deck_senses_require_deck")
    return node


async def _delete_prior_defsets(prior: dict[UUID, int]) -> None:
    try:
        await cache.delete_prior_defsets(prior)
    except Exception:
        pass
