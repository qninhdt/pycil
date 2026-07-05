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
from pycil.hierarchy.models import DeckAttributes, Node, NodeType


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
    node = Node(
        author_id=author_id,
        type=NodeType.DECK,
        parent_node_id=parent_node_id,
        name=name,
    )
    session.add(node)
    await session.flush()
    session.add(DeckAttributes(node_id=node.id))
    await session.commit()
    await session.refresh(node)
    return node


async def rename_deck(session: AsyncSession, node: Node, name: str) -> Node:
    node.name = name
    await session.commit()
    await session.refresh(node)
    return node


async def delete_deck(session: AsyncSession, node: Node) -> None:
    """Soft-delete a deck node."""
    from datetime import UTC, datetime

    node.deleted_at = datetime.now(UTC)
    await session.commit()


async def add_sense(session: AsyncSession, node_id: UUID, sense_id: int) -> DeckSense:
    """Append a sense to a deck (idempotent on the UNIQUE(node_id, sense_id))."""
    existing = await session.execute(
        select(DeckSense).where(
            DeckSense.node_id == node_id, DeckSense.sense_id == sense_id
        )
    )
    row = existing.scalars().first()
    if row is not None:
        return row
    next_pos = await _next_position(session, node_id)
    row = DeckSense(node_id=node_id, sense_id=sense_id, position=next_pos)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def remove_sense(session: AsyncSession, node_id: UUID, sense_id: int) -> None:
    await session.execute(
        delete(DeckSense).where(
            DeckSense.node_id == node_id, DeckSense.sense_id == sense_id
        )
    )
    await session.commit()


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
        select(func.coalesce(func.max(DeckSense.position), -1)).where(
            DeckSense.node_id == node_id
        )
    )
    return int(result.scalar_one()) + 1
