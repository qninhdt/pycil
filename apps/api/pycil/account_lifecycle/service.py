"""Bounded export and deletion of data owned by a single Pycil account."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth import refresh_sessions

# (table to probe, statement). The prefix match is parameterized; only the table name
# is fixed, and it is fixed here rather than interpolated at the call site.
_CHECKPOINT_DELETES = (
    ("checkpoint_writes", "DELETE FROM checkpoint_writes WHERE thread_id LIKE :checkpoint_prefix"),
    ("checkpoint_blobs", "DELETE FROM checkpoint_blobs WHERE thread_id LIKE :checkpoint_prefix"),
    ("checkpoints", "DELETE FROM checkpoints WHERE thread_id LIKE :checkpoint_prefix"),
)


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
    digest = refresh_sessions.token_digest(raw_token)
    row = await session.scalar(
        text(
            "SELECT 1 FROM refresh_sessions WHERE user_id = :user_id AND token_digest = :digest "
            "AND revoked_at IS NULL AND expires_at > NOW()"
        ),
        {"user_id": user_id, "digest": digest},
    )
    return row is not None


async def delete_account(session: AsyncSession, user_id: UUID) -> None:
    """Erase dependent Pycil rows in FK order, never touching Lexi's database."""
    # Revoke before any irreversible deletion so a failed cleanup cannot leave
    # active credentials. The whole operation remains a single DB transaction.
    await refresh_sessions.revoke_user_sessions(session, user_id)
    statements = (
        # The audit row survives the action it describes (`action_id` is SET NULL),
        # so account deletion has to remove this account's audits explicitly —
        # both the ones it is the actor of and the ones describing its own actions.
        "DELETE FROM assistant_action_audit WHERE actor_id = :user_id OR action_id IN "
        "(SELECT id FROM assistant_actions WHERE owner_id = :user_id)",
        # Runs, their events and their actions cascade from the thread (0024), so only
        # the root needs naming. `owner_id` is still NO ACTION on purpose: account
        # deletion must fail loudly if a table is forgotten, which is exactly what
        # surfaced the four missing statements here.
        "DELETE FROM assistant_threads WHERE owner_id = :user_id",
        "DELETE FROM session_sense_attempts WHERE user_id = :user_id",
        "DELETE FROM responses WHERE user_id = :user_id",
        "DELETE FROM review_log WHERE user_id = :user_id",
        "DELETE FROM user_sense_stats WHERE user_id = :user_id",
        "DELETE FROM user_learning_settings WHERE user_id = :user_id",
        "DELETE FROM session_summaries WHERE user_id = :user_id",
        # Async task rows. Every FK onto `users` is NO ACTION, so omitting these
        # does not orphan a row — it aborts the whole deletion and the account
        # survives. Both tables are per-requester, and no task is shared between
        # users (`uq_task_interest_provenance` is per requester), so this erases
        # only this account's participation.
        #
        # `async_tasks` itself is deliberately left in place: it is keyed by a
        # server-derived work key, carries no `users` FK, and its `word` rows are
        # reusable dictionary work that outlives any one requester. A `grading`
        # task's `result` does hold that learner's own feedback text, so those are
        # removed with their interests.
        "DELETE FROM async_command_receipts WHERE requester_id = :user_id",
        "DELETE FROM async_task_outbox WHERE event_id IN "
        "(SELECT id FROM async_task_events WHERE task_id IN "
        "(SELECT i.task_id FROM async_task_interests i JOIN async_tasks t ON t.id = i.task_id "
        "WHERE i.requester_id = :user_id AND t.kind = 'grading'))",
        "DELETE FROM async_task_events WHERE task_id IN "
        "(SELECT i.task_id FROM async_task_interests i JOIN async_tasks t ON t.id = i.task_id "
        "WHERE i.requester_id = :user_id AND t.kind = 'grading')",
        "DELETE FROM async_task_interests WHERE requester_id = :user_id",
        # The `NOT IN` guard, not the `kind` filter, is what keeps a task another
        # reader still references. Both source columns are NOT NULL, so the
        # `NOT IN`/NULL trap that would silently delete nothing cannot arise.
        "DELETE FROM async_tasks WHERE kind = 'grading' AND id NOT IN "
        "(SELECT task_id FROM async_task_interests "
        "UNION SELECT task_id FROM async_command_receipts)",
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
    # LangGraph owns the checkpoint tables and keys them by a `thread_id` string
    # rather than a foreign key, so no cascade reaches them and these deletions have
    # to stay. Written as literals rather than interpolated from a table list: the
    # values were always parameterized, but nothing about an f-string says so.
    #
    # `to_regclass` first because the tables are migration-owned: an old local
    # database may predate the assistant migration, and deletion must stay retry-safe.
    for table, statement in _CHECKPOINT_DELETES:
        if await session.scalar(text("SELECT to_regclass(:table)"), {"table": table}):
            await session.execute(text(statement), params)
    await session.commit()
