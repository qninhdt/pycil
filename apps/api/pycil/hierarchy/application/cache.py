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
from pycil.hierarchy.application.ancestry import ancestor_chain
from pycil.hierarchy.infra.models import Node

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
        affected.update(await ancestor_chain(session, node_id))

    references = await session.execute(
        select(Node.id).where(Node.target_node_id.in_(changed))
    )
    for reference_id in references.scalars():
        affected.update(await ancestor_chain(session, reference_id))

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
    """Best-effort cleanup after commit; correctness does not depend on Redis.

    Deletes the anonymous key *and* every per-viewer variant. It used to build only
    `_defset_key(node_id, generation)` — with no `viewer_id` — while every writer
    (`hierarchy/router.py:62`, `hierarchy/viewer_stats.py:28`) sets the key *with*
    `viewer_id=`. So cleanup reached the one key nobody writes and left the real
    ones to expire on their own. Correctness held, because the generation is part
    of the key and a bumped generation makes the old value unreachable — but the
    leak is nodes x viewers x mutations, all of it retained for the full hour of
    `_TTL`.

    A SCAN per node rather than a KEYS over the whole database: SCAN is cursored
    and non-blocking, and the prefix is exact up to the viewer suffix, so each pass
    touches only the keys for one (node, generation).
    """
    if not prior_generations:
        return

    redis = get_redis()
    doomed: list[str] = []
    for node_id, generation in prior_generations.items():
        anonymous = _defset_key(node_id, generation)
        doomed.append(anonymous)
        # `_defset_key` appends ":viewer:<uuid>", so the anonymous key is a strict
        # prefix of every per-viewer key for the same node and generation.
        async for key in redis.scan_iter(match=f"{anonymous}:viewer:*", count=100):
            doomed.append(key)

    if doomed:
        await redis.delete(*doomed)


async def delete_prior_defsets_quietly(prior_generations: dict[UUID, int]) -> None:
    """`delete_prior_defsets`, with Redis failures swallowed.

    Callers run this *after* the database commit, so a Redis outage must not
    surface as a failed mutation the caller would retry — the write already
    happened, and the generation bump already made the stale values unreachable.

    Lives here rather than in each service: `hierarchy/service.py` and
    `content/service.py` each carried a byte-identical private copy, and only one
    of them kept the comment explaining why the exception is swallowed.
    """
    try:
        await delete_prior_defsets(prior_generations)
    except Exception:
        # Redis is a cache; a post-commit cleanup failure cannot undo a DB write.
        pass
