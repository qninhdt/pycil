"""GDPR data-retention purge.

Explicitly deletes user-owned PII rows for accounts soft-deleted more than
the grace window ago (`users.deleted_at < now() - 14 days`), the same cutoff
the hard-delete cron uses. Runs as the first step of that cron, before the
`users` row itself is removed: this gives an auditable per-table delete count
for PII that would otherwise vanish silently via FK cascade (and covers the
few child tables whose FK is SET NULL / no-cascade rather than CASCADE).
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_log = logging.getLogger(__name__)


# Retention grace window: matches user_service.hard_delete_expired (14 days).
_GRACE_DAYS = 14

_PURGE_TABLES = [
    "activity_events",
    "definition_overrides",
    "term_notes",
    "user_term_jobs",
    "user_term_stats",
    "user_definition_stats",
    "user_tos_acks",
    "deck_likes",
    "follows",
    "push_subscriptions",
]


async def purge_due(session: AsyncSession) -> dict[str, int]:
    """Purge PII rows for accounts soft-deleted past the grace window.

    Driven by `users.deleted_at < now() - 14d`. Does NOT delete the `users`
    rows themselves — the hard-delete cron does that immediately after, and
    most child tables also CASCADE. This pass guarantees an auditable,
    explicit delete of PII in tables whose FK is SET NULL / non-cascading.
    Caller owns transaction commit semantics.
    """
    targets = (
        await session.execute(
            text(
                "SELECT id FROM users "
                "WHERE deleted_at IS NOT NULL "
                "  AND deleted_at < NOW() - make_interval(days => :grace)"
            ),
            {"grace": _GRACE_DAYS},
        )
    ).all()
    if not targets:
        return {}
    user_ids = [r.id for r in targets]
    counts: dict[str, int] = {}
    for table in _PURGE_TABLES:
        col = "follower_id" if table == "follows" else "user_id"
        result = await session.execute(
            text(f"DELETE FROM {table} WHERE {col} = ANY(:ids)"),
            {"ids": user_ids},
        )
        counts[table] = int(getattr(result, "rowcount", 0) or 0)
    _log.info("data_retention_purge", extra={"counts": counts})
    return counts
