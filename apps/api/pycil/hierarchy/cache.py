"""L1 cache: user-agnostic sense-id set + CEFR counts per node.

L1 ONLY for MVP — uncached stats already meet the <50ms target, so there is no
per-user L2 cache and NO review-coupled invalidation. Structural edits (move,
add/remove sense, delete) bust the edited node's key plus every ancestor's key
(O(depth) walk up ``parent_node_id``). Add L2 later behind measured load.
"""

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.db.redis import get_redis
from pycil.hierarchy.models import Node

_TTL = 3600


def _defset_key(node_id: UUID) -> str:
    return f"node:{node_id}:defset"


async def get_defset(node_id: UUID) -> list[int] | None:
    raw = await get_redis().get(_defset_key(node_id))
    return json.loads(raw) if raw else None


async def set_defset(node_id: UUID, sense_ids: list[int]) -> None:
    await get_redis().set(_defset_key(node_id), json.dumps(sense_ids), ex=_TTL)


async def bust_ancestors(session: AsyncSession, node_id: UUID) -> None:
    """Bust the node's L1 key and every ancestor's (O(depth) up the tree)."""
    redis = get_redis()
    current: UUID | None = node_id
    seen: set[UUID] = set()
    while current is not None and current not in seen:
        seen.add(current)
        await redis.delete(_defset_key(current))
        parent = await session.execute(
            select(Node.parent_node_id).where(Node.id == current)
        )
        current = parent.scalar_one_or_none()
