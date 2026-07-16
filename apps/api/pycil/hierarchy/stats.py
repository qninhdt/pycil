"""Stage-2 stats: overlay a Stage-1 sense-id set against user_sense_stats.

All queries stay inside pycil's DB. CEFR distribution resolves sense content via
the LexiClient (never a cross-DB JOIN). Stats join against a VALUES set rather
than ``= ANY(bigarray)`` for index-friendly plans (design §10).
"""

from collections import Counter
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.content.lexi_port import LexiClient

_MASTERED_DEFAULT = 80


@dataclass
class FolderStats:
    total: int
    learned: int
    mastered: int
    avg_mastery: float


@dataclass
class WeakSense:
    sense_id: int
    mastery: int


async def folder_stats(
    session: AsyncSession,
    user_id: UUID,
    sense_ids: list[int],
    *,
    mastered_threshold: int = _MASTERED_DEFAULT,
) -> FolderStats:
    """{total, learned, mastered, avg_mastery} for a user over a sense-id set."""
    total = len(sense_ids)
    if total == 0:
        return FolderStats(total=0, learned=0, mastered=0, avg_mastery=0.0)

    stmt = text(
        """
        SELECT
            COUNT(*) FILTER (WHERE uss.review_count > 0) AS learned,
            COALESCE(SUM(CASE
                WHEN uss.review_count > 0 AND uss.mastery >= :thresh THEN 1
                ELSE 0
            END), 0) AS mastered,
            COALESCE(AVG(uss.mastery) FILTER (WHERE uss.review_count > 0), 0) AS avg_mastery
        FROM user_sense_stats uss
        WHERE uss.user_id = :user_id AND uss.sense_id = ANY(CAST(:sense_ids AS bigint[]))
        """
    )
    row = (
        await session.execute(
            stmt, {"user_id": str(user_id), "thresh": mastered_threshold, "sense_ids": sense_ids}
        )
    ).one()
    return FolderStats(
        total=total,
        learned=int(row.learned),
        mastered=int(row.mastered),
        avg_mastery=round(float(row.avg_mastery), 2),
    )


async def weakest_senses(
    session: AsyncSession, user_id: UUID, sense_ids: list[int], *, limit: int = 10
) -> list[WeakSense]:
    """Top-N learned senses by mastery ascending (the user's weakest)."""
    if not sense_ids:
        return []
    stmt = text(
        """
        SELECT sense_id, mastery FROM user_sense_stats
        WHERE user_id = :user_id
          AND sense_id = ANY(CAST(:sense_ids AS bigint[]))
          AND review_count > 0
          AND (buried_until IS NULL OR buried_until <= NOW())
        ORDER BY mastery ASC, sense_id ASC
        LIMIT :limit
        """
    )
    rows = await session.execute(
        stmt, {"user_id": str(user_id), "sense_ids": sense_ids, "limit": limit}
    )
    return [WeakSense(sense_id=r.sense_id, mastery=r.mastery) for r in rows]


async def cefr_distribution(client: LexiClient, sense_ids: list[int]) -> dict[str, int]:
    """Bucket a sense-id set by CEFR level via the port (NOT a cross-DB JOIN)."""
    if not sense_ids:
        return {}
    views = await client.get_senses(sense_ids)
    counts: Counter[str] = Counter()
    for v in views:
        counts[v.cefr_level or "unknown"] += 1
    return dict(counts)
