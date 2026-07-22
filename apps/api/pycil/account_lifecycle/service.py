"""Bounded export and deletion of data owned by a single Pycil account."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth import refresh_sessions


async def export_account(session: AsyncSession, user_id: UUID) -> dict:
    """Return Pycil-owned records only; Lexi's dictionary is never queried."""
    async def rows(statement: str) -> list[dict]:
        result = await session.execute(text(statement), {"user_id": user_id})
        return [dict(row) for row in result.mappings()]

    profile = (
        await rows("SELECT id, email, name, image, created_at FROM users WHERE id = :user_id")
    )[0]
    nodes = await rows(
        "SELECT id, type, parent_node_id, target_node_id, name, description, visibility, "
        "created_at, updated_at FROM nodes WHERE author_id = :user_id"
    )
    deck_senses = await rows(
        "SELECT ds.node_id, ds.sense_id, ds.position FROM deck_senses ds "
        "JOIN nodes n ON n.id = ds.node_id WHERE n.author_id = :user_id"
    )
    return {
        "profile": profile,
        "hierarchy": [
            {**node, "senses": [s for s in deck_senses if s["node_id"] == node["id"]]}
            for node in nodes
        ],
        "learning": {
            "sense_stats": await rows("SELECT * FROM user_sense_stats WHERE user_id = :user_id"),
            "review_log": await rows("SELECT * FROM review_log WHERE user_id = :user_id"),
            "responses": await rows("SELECT * FROM responses WHERE user_id = :user_id"),
        },
        "word_generations": await rows(
            "SELECT id, query, status, result, error_code, created_at, updated_at "
            "FROM word_generations WHERE owner_id = :user_id"
        ),
        "assistant": {
            "threads": await rows(
                "SELECT id, title, status, created_at, updated_at FROM assistant_threads "
                "WHERE owner_id = :user_id"
            ),
            "actions": await rows(
                "SELECT id, tool, status, result, created_at, updated_at FROM assistant_actions "
                "WHERE owner_id = :user_id"
            ),
        },
    }


async def owns_active_refresh_token(session: AsyncSession, user_id: UUID, raw_token: str) -> bool:
    digest = refresh_sessions._digest(raw_token)
    row = await session.scalar(
        text(
            "SELECT 1 FROM refresh_sessions WHERE user_id = :user_id AND token_digest = :digest "
            "AND revoked_at IS NULL AND expires_at > NOW()"
        ),
        {"user_id": user_id, "digest": digest},
    )
    return row is not None


async def delete_account(session: AsyncSession, user_id: UUID) -> int:
    """Erase dependent Pycil rows in FK order, never touching Lexi's database."""
    # Revoke before any irreversible deletion so a failed cleanup cannot leave
    # active credentials. The whole operation remains a single DB transaction.
    await refresh_sessions.revoke_user_sessions(session, user_id)
    inflight_jobs = await session.scalar(
        text(
            "SELECT count(*) FROM word_generations WHERE owner_id = :user_id "
            "AND status IN ('queued', 'running')"
        ),
        {"user_id": user_id},
    )
    statements = (
        "DELETE FROM assistant_action_audit WHERE actor_id = :user_id OR action_id IN "
        "(SELECT id FROM assistant_actions WHERE owner_id = :user_id)",
        "DELETE FROM assistant_run_events WHERE run_id IN "
        "(SELECT id FROM assistant_runs WHERE owner_id = :user_id)",
        "DELETE FROM assistant_actions WHERE owner_id = :user_id",
        "DELETE FROM assistant_runs WHERE owner_id = :user_id",
        "DELETE FROM assistant_threads WHERE owner_id = :user_id",
        "DELETE FROM session_sense_attempts WHERE user_id = :user_id",
        "DELETE FROM responses WHERE user_id = :user_id",
        "DELETE FROM review_log WHERE user_id = :user_id",
        "DELETE FROM user_sense_stats WHERE user_id = :user_id",
        "DELETE FROM word_generations WHERE owner_id = :user_id",
        "DELETE FROM deck_senses WHERE node_id IN "
        "(SELECT id FROM nodes WHERE author_id = :user_id)",
        "DELETE FROM deck_attributes WHERE node_id IN "
        "(SELECT id FROM nodes WHERE author_id = :user_id)",
        # Public decks may be referenced by another owner. A reference has no
        # independent meaning after its target is erased, so delete the
        # dependent pointer (never the other user's folder or deck).
        "DELETE FROM nodes WHERE type = 'REFERENCE' AND target_node_id IN "
        "(SELECT id FROM nodes WHERE author_id = :user_id)",
        "DELETE FROM nodes WHERE author_id = :user_id",
        "DELETE FROM refresh_sessions WHERE user_id = :user_id",
        "DELETE FROM users WHERE id = :user_id",
    )
    params = {"user_id": user_id, "checkpoint_prefix": f"assistant:{user_id}:%"}
    for statement in statements:
        await session.execute(text(statement), params)
    # Checkpoint tables are migration-owned rather than ORM metadata. Old local
    # databases may predate the assistant migration, so make deletion retry-safe.
    for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
        exists = await session.scalar(text("SELECT to_regclass(:table)"), {"table": table})
        if exists:
            await session.execute(
                text(f"DELETE FROM {table} WHERE thread_id LIKE :checkpoint_prefix"), params
            )
    await session.commit()
    return int(inflight_jobs or 0)
