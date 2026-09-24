"""Stage-2 stats: overlay a Stage-1 sense-id set against user_sense_stats.

All queries stay inside pycil's DB. CEFR distribution resolves sense content via
the LexiReader (never a cross-DB JOIN). Stats join against a VALUES set rather
than ``= ANY(bigarray)`` for index-friendly plans (design §10).
"""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.policy.history import DailyHistoryBucket, MasteryObservation, daily_history
from pycil.policy.policy import MASTERED_FLOOR
from pycil.ports.lexi import LexiReader

# How many sense ids cross the Lexi boundary in one `get_senses()` call. Large
# enough that a normal learner is a single round trip, small enough that a heavy
# account cannot build one query out of its entire tracked set.
_CEFR_CHUNK = 500


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


async def stats_for_scope(
    session: AsyncSession,
    user_id: UUID,
    sense_ids: list[int] | None,
    *,
    mastered_threshold: int = MASTERED_FLOOR,
) -> FolderStats:
    """Return totals for a node sense set, or the whole account when ``None``.

    Both scopes use the same learned predicate: ``status = 'scheduled'``. A node
    scope counts its canonical distinct live sense set even when the learner has no
    row yet; the account scope is the same relation without the scope filter.
    """
    if sense_ids is not None and not sense_ids:
        return FolderStats(total=0, learned=0, mastered=0, avg_mastery=0.0)

    if sense_ids is None:
        statement = """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE uss.status = 'scheduled') AS learned,
                COUNT(*) FILTER (
                    WHERE uss.status = 'scheduled' AND uss.mastery >= :thresh
                ) AS mastered,
                COALESCE(AVG(uss.mastery) FILTER (WHERE uss.status = 'scheduled'), 0)
                    AS avg_mastery
            FROM user_sense_stats uss
            WHERE uss.user_id = :user_id
        """
        params = {"user_id": str(user_id), "thresh": mastered_threshold}
    else:
        statement = """
            WITH scoped AS (
                SELECT DISTINCT unnest(CAST(:sense_ids AS bigint[])) AS sense_id
            )
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE uss.status = 'scheduled') AS learned,
                COUNT(*) FILTER (
                    WHERE uss.status = 'scheduled' AND uss.mastery >= :thresh
                ) AS mastered,
                COALESCE(AVG(uss.mastery) FILTER (WHERE uss.status = 'scheduled'), 0)
                    AS avg_mastery
            FROM scoped
            LEFT JOIN user_sense_stats uss
              ON uss.user_id = :user_id AND uss.sense_id = scoped.sense_id
        """
        params = {
            "user_id": str(user_id),
            "thresh": mastered_threshold,
            "sense_ids": sense_ids,
        }
    row = (await session.execute(text(statement), params)).one()
    return FolderStats(
        total=int(row.total),
        learned=int(row.learned),
        mastered=int(row.mastered),
        avg_mastery=round(float(row.avg_mastery), 2),
    )


async def weakest_senses(
    session: AsyncSession,
    user_id: UUID,
    sense_ids: list[int] | None,
    *,
    limit: int = 10,
) -> list[WeakSense]:
    """Exact database top-K for a node scope or the whole account.

    The node scope joins against a de-duplicated ``VALUES`` set rather than
    ``sense_id = ANY(bigint[])`` (design §10): the same index-friendly shape
    ``stats_for_scope`` uses, so the planner drives the scan from
    ``user_sense_stats`` instead of testing every row against a scalar array.
    """
    if sense_ids is not None and not sense_ids:
        return []

    if sense_ids is None:
        statement = """
            SELECT sense_id, mastery FROM user_sense_stats
            WHERE user_id = :user_id
              AND status = 'scheduled'
            ORDER BY mastery ASC, sense_id ASC
            LIMIT :limit
        """
        params: dict = {"user_id": str(user_id), "limit": limit}
    else:
        statement = """
            WITH scoped AS (
                SELECT DISTINCT unnest(CAST(:sense_ids AS bigint[])) AS sense_id
            )
            SELECT uss.sense_id, uss.mastery
            FROM scoped
            JOIN user_sense_stats uss
              ON uss.user_id = :user_id AND uss.sense_id = scoped.sense_id
            WHERE uss.status = 'scheduled'
            ORDER BY uss.mastery ASC, uss.sense_id ASC
            LIMIT :limit
        """
        params = {"user_id": str(user_id), "limit": limit, "sense_ids": sense_ids}
    rows = await session.execute(text(statement), params)
    return [WeakSense(sense_id=r.sense_id, mastery=r.mastery) for r in rows]


async def cefr_distribution(client: LexiReader, sense_ids: list[int]) -> dict[str, int]:
    """Bucket a sense-id set by CEFR level via the port (NOT a cross-DB JOIN).

    Chunked, because the level lives only in Lexi: pycil stores no `cefr_level`,
    so this cannot be a `GROUP BY` and the ids genuinely have to cross the
    boundary. A single `get_senses()` call with the caller's whole tracked set
    became one enormous query as that set grew; `_CEFR_CHUNK` bounds each call
    while the totals stay identical, since bucketing a union is the sum of
    bucketing its parts.
    """
    if not sense_ids:
        return {}
    counts: Counter[str] = Counter()
    for offset in range(0, len(sense_ids), _CEFR_CHUNK):
        chunk = sense_ids[offset : offset + _CEFR_CHUNK]
        for v in await client.get_senses(chunk):
            counts[v.cefr_level or "unknown"] += 1
    return dict(counts)


async def deck_item_counts(session: AsyncSession, node_ids: list[UUID]) -> dict[UUID, int]:
    """Sense counts for the given decks in ONE grouped aggregate.

    Deliberately not the cached subtree path: that resolves the whole authorized deck
    set under a root — a recursive walk, a readability check and a Redis read per
    deck — all bound to a single root. Looping it over a 50-row page is ~250 round
    trips. Folder aggregates and due counts are therefore not served on the list
    response at all; they belong on the opened node, where the membership cache
    applies.

    Moved out of the router: it is a grouped aggregate over `deck_senses`, which is
    data access, and routers here are meant to be thin.
    """
    if not node_ids:
        return {}
    rows = await session.execute(
        text(
            """
            SELECT node_id, count(*) AS items FROM deck_senses
            WHERE node_id = ANY(CAST(:node_ids AS uuid[]))
            GROUP BY node_id
            """
        ),
        {"node_ids": [str(node_id) for node_id in node_ids]},
    )
    return {row.node_id: int(row.items) for row in rows}


async def history_buckets(
    session: AsyncSession,
    user_id: UUID,
    sense_ids: list[int] | None,
    start: date,
    end: date,
) -> list[DailyHistoryBucket]:
    """Day-bucketed review history over a sense set, carrying the pre-window
    baseline forward so an untouched day reports the mastery it inherited.

    `sense_ids=None` means the caller's WHOLE tracked set. That is expressed as a
    correlated subquery over `user_sense_stats` rather than by listing the ids:
    the global scope is "every sense this user has state for", which is a
    predicate, and materialising it in Python only to send it back as a
    `bigint[]` moved the entire set across the wire twice. Both tables live in the
    same database, so the subquery costs nothing extra.
    """
    if sense_ids is not None and not sense_ids:
        return [
            DailyHistoryBucket(day=day, reviewed=0, avg_mastery=0.0)
            for day in (start + timedelta(days=offset) for offset in range((end - start).days + 1))
        ]
    start_at = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    end_at = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    # One predicate, two queries. `user_sense_stats` holds one row per
    # (user, sense), so the subquery cannot duplicate a `review_log` row — the
    # same guarantee the SELECT DISTINCT in `_tracked_sense_ids` used to provide.
    if sense_ids is None:
        scope = """
              AND EXISTS (
                  SELECT 1 FROM user_sense_stats s
                  WHERE s.user_id = review_log.user_id
                    AND s.sense_id = review_log.sense_id
              )
        """
        scope_params: dict = {}
    else:
        scope = "AND sense_id = ANY(CAST(:sense_ids AS bigint[]))"
        scope_params = {"sense_ids": sense_ids}

    baseline_rows = await session.execute(
        text(
            f"""
            SELECT DISTINCT ON (sense_id) sense_id, mastery_after
            FROM review_log
            WHERE user_id = :user_id
              {scope}
              AND reviewed_at < :start_at
            ORDER BY sense_id, reviewed_at DESC, id DESC
            """
        ),
        {"user_id": str(user_id), "start_at": start_at, **scope_params},
    )
    event_rows = await session.execute(
        text(
            f"""
            SELECT sense_id, reviewed_at, mastery_after
            FROM review_log
            WHERE user_id = :user_id
              {scope}
              AND reviewed_at >= :start_at AND reviewed_at < :end_at
            ORDER BY reviewed_at, id
            """
        ),
        {
            "user_id": str(user_id),
            "start_at": start_at,
            "end_at": end_at,
            **scope_params,
        },
    )
    baseline = {int(row.sense_id): int(row.mastery_after) for row in baseline_rows}
    events = [
        MasteryObservation(int(row.sense_id), row.reviewed_at, int(row.mastery_after))
        for row in event_rows
    ]
    return daily_history(start, end, baseline, events)
