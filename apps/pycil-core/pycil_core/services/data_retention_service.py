"""Data retention automation (P12 phase 5).

Periodic cron that physically deletes user-owned rows whose owner
flagged delete_after_at and the date has elapsed. Distinct from soft
"users.deleted_at" — this fires after the GDPR-mandated grace window
expires.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_log = logging.getLogger(__name__)


_PURGE_TABLES = [
    "activity_events",
    "definition_overrides",
    "term_notes",
    "saved_searches",
    "user_term_jobs",
    "user_term_stats",
    "user_definition_stats",
    "user_tos_acks",
    "deck_likes",
    "follows",
    "classroom_members",
    "push_subscriptions",
]


async def purge_due(session: AsyncSession) -> dict[str, int]:
    """Run a single purge pass; return per-table delete counts.

    Driven by users.delete_after_at <= now(). Caller is responsible
    for transaction commit semantics — service runs inside a fresh
    autocommit-style block in the cron.
    """
    targets = (
        await session.execute(
            text(
                "SELECT id FROM users "
                "WHERE delete_after_at IS NOT NULL "
                "  AND delete_after_at <= NOW()"
            )
        )
    ).all()
    if not targets:
        return {}
    user_ids = [r.id for r in targets]
    counts: dict[str, int] = {}
    for table in _PURGE_TABLES:
        col = "follower_id" if table == "follows" else (
            "target_user_id" if table == "admin_actions" else "user_id"
        )
        result = await session.execute(
            text(f"DELETE FROM {table} WHERE {col} = ANY(:ids)"),
            {"ids": user_ids},
        )
        counts[table] = int(getattr(result, "rowcount", 0) or 0)
    result = await session.execute(
        text("DELETE FROM users WHERE id = ANY(:ids)"),
        {"ids": user_ids},
    )
    counts["users"] = int(getattr(result, "rowcount", 0) or 0)
    _log.info("data_retention_purge", extra={"counts": counts})
    return counts
