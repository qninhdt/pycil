"""Generation-safe L1 cache for canonical subtree sense sets.

PostgreSQL is authoritative for structural generations. Redis deletion is only a
best-effort cleanup: stale values are unreachable because every key includes the
generation committed with the structural mutation.
"""

import json
from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.db.redis import get_redis
from pycil.hierarchy.models import Node

_TTL = 3600


def _defset_key(node_id: UUID, generation: int, viewer_id: UUID | None = None) -> str:
    viewer_suffix = f":viewer:{viewer_id}" if viewer_id is not None else ""
    return f"node:{node_id}:defset:v{generation}{viewer_suffix}"


async def get_defset(
    node_id: UUID, generation: int, *, viewer_id: UUID | None = None
) -> list[int] | None:
    raw = await get_redis().get(_defset_key(node_id, generation, viewer_id))
    return json.loads(raw) if raw else None


async def set_defset(
    node_id: UUID,
    sense_ids: list[int],
    *,
    generation: int,
    viewer_id: UUID | None = None,
) -> None:
    """Write a value that is valid only for the supplied DB generation."""
    await get_redis().set(
        _defset_key(node_id, generation, viewer_id), json.dumps(sense_ids), ex=_TTL
    )


async def current_generation(session: AsyncSession, node_id: UUID) -> int | None:
    result = await session.execute(
        select(Node.structural_generation).where(Node.id == node_id)
    )
    return result.scalar_one_or_none()


async def bump_generations(
    session: AsyncSession, changed_node_ids: Iterable[UUID]
) -> dict[UUID, int]:
    """Increment direct and reverse-reference ancestor generations in-transaction."""
    changed = {node_id for node_id in changed_node_ids if node_id is not None}
    if not changed:
        return {}

    affected = set(changed)
    for node_id in tuple(changed):
        affected.update(await _ancestor_ids(session, node_id))

    references = await session.execute(
        select(Node.id).where(Node.target_node_id.in_(changed))
    )
    for reference_id in references.scalars():
        affected.update(await _ancestor_ids(session, reference_id))

    rows = await session.execute(
        select(Node.id, Node.structural_generation).where(Node.id.in_(affected))
    )
    prior = {node_id: generation for node_id, generation in rows}
    if prior:
        await session.execute(
            update(Node)
            .where(Node.id.in_(prior))
            .values(structural_generation=Node.structural_generation + 1)
        )
    return prior


async def delete_prior_defsets(prior_generations: dict[UUID, int]) -> None:
    """Best-effort cleanup after commit; correctness does not depend on Redis."""
    if prior_generations:
        await get_redis().delete(
            *[
                _defset_key(node_id, generation)
                for node_id, generation in prior_generations.items()
            ]
        )


async def _ancestor_ids(session: AsyncSession, node_id: UUID) -> set[UUID]:
    ancestors: set[UUID] = set()
    current: UUID | None = node_id
    while current is not None and current not in ancestors:
        ancestors.add(current)
        result = await session.execute(
            select(Node.parent_node_id).where(Node.id == current)
        )
        current = result.scalar_one_or_none()
    return ancestors
