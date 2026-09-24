"""Account export and hand-ordered deletion."""

from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account import credit
from pycil.auth.deps import evict_mapping
from pycil.auth.models import User
from pycil.common.errors import NotFoundError, ServiceUnavailableError
from pycil.config import settings
from pycil.db.redis import get_redis

# LangGraph owns these tables outside SQLModel metadata.  They are optional on a
# fresh API-only database, so probing their registration is intentional; all
# application-owned tables below are named directly and therefore fail loudly if
# their deletion step is ever forgotten.
_CHECKPOINT_DELETES = (
    ("checkpoint_writes", "DELETE FROM checkpoint_writes WHERE thread_id LIKE :checkpoint_prefix"),
    ("checkpoint_blobs", "DELETE FROM checkpoint_blobs WHERE thread_id LIKE :checkpoint_prefix"),
    ("checkpoints", "DELETE FROM checkpoints WHERE thread_id LIKE :checkpoint_prefix"),
)


async def _rows(session: AsyncSession, statement: str, params: dict | None = None) -> list[dict]:
    result = await session.execute(text(statement), params or {})
    return [dict(row) for row in result.mappings()]


async def export_account(session: AsyncSession, user_id: UUID) -> dict:
    """Return owner-scoped Pycil data and opaque Lexi ids, never dictionary rows."""
    profile_rows = await _rows(
        session,
        "SELECT id, email, name, image, clerk_id, created_at FROM users WHERE id = :user_id",
        {"user_id": user_id},
    )
    if not profile_rows:
        raise NotFoundError("account_not_found")
    profile = profile_rows[0]
    # The Clerk subject is the external sign-in handle. It is reported as a single
    # value rather than an identity list, because Clerk owns the identity provider
    # and Pycil keeps no per-provider rows of its own.

    nodes = await _rows(
        session,
        "SELECT id, type, parent_node_id, target_node_id, name, description, visibility, "
        "created_at, updated_at FROM nodes WHERE author_id = :user_id",
        {"user_id": user_id},
    )
    deck_senses = await _rows(
        session,
        "SELECT ds.node_id, ds.sense_id, ds.position FROM deck_senses ds "
        "JOIN nodes n ON n.id = ds.node_id WHERE n.author_id = :user_id",
        {"user_id": user_id},
    )
    credit_snapshot = await credit.snapshot(session, user_id)

    return {
        "profile": profile,
        "hierarchy": [
            {**node, "senses": [s for s in deck_senses if s["node_id"] == node["id"]]}
            for node in nodes
        ],
        "learning": {
            "sense_stats": await _rows(
                session,
                "SELECT * FROM user_sense_stats WHERE user_id = :user_id",
                {"user_id": user_id},
            ),
            "review_log": await _rows(
                session, "SELECT * FROM review_log WHERE user_id = :user_id", {"user_id": user_id}
            ),
            "responses": await _rows(
                session, "SELECT * FROM responses WHERE user_id = :user_id", {"user_id": user_id}
            ),
            "settings": await _rows(
                session,
                "SELECT * FROM user_learning_settings WHERE user_id = :user_id",
                {"user_id": user_id},
            ),
            "session_summaries": await _rows(
                session,
                "SELECT * FROM session_summaries WHERE user_id = :user_id",
                {"user_id": user_id},
            ),
        },
        "assistant": {
            "threads": await _rows(
                session,
                "SELECT id, title, status, created_at, updated_at FROM assistant_threads "
                "WHERE owner_id = :user_id",
                {"user_id": user_id},
            ),
        },
        "plan": credit_snapshot.plan,
        "credit": credit_snapshot.as_dict(),
    }


async def _owned_node_order(session: AsyncSession, user_id: UUID) -> list[UUID]:
    result = await session.execute(
        text("SELECT id, parent_node_id FROM nodes WHERE author_id = :user_id"),
        {"user_id": user_id},
    )
    parents = {row[0]: row[1] for row in result}
    depths: dict[UUID, int] = {}

    def depth(node_id: UUID, visiting: set[UUID]) -> int:
        if node_id in depths:
            return depths[node_id]
        if node_id in visiting:
            raise RuntimeError("account_node_cycle")
        visiting.add(node_id)
        parent_id = parents[node_id]
        value = 0 if parent_id not in parents else depth(parent_id, visiting) + 1
        visiting.remove(node_id)
        depths[node_id] = value
        return value

    for node_id in parents:
        depth(node_id, set())
    return sorted(parents, key=lambda node_id: (depths[node_id], str(node_id)), reverse=True)


async def delete_account(session: AsyncSession, user_id: UUID) -> None:
    """Delete one account in explicit owner order; unknown FKs abort the transaction.

    Pycil owns no session state, so there is nothing local to revoke. The external
    Clerk identity is removed *before* the local rows, because Clerk is the sign-in
    authority: while the subject still exists the next sign-in just-in-time
    provisions a fresh empty account, so removing the rows first would resurrect the
    learner. A failure after the subject is gone leaves unreachable rows that a
    retry can still finish.
    """
    # Assistant threads and their checkpoints. A turn in flight is bounded by a
    # Redis lease that expires on its own, so there is no run row to cancel.
    await session.execute(
        text("DELETE FROM assistant_threads WHERE owner_id = :user_id"), {"user_id": user_id}
    )
    params = {"user_id": user_id, "checkpoint_prefix": f"assistant:{user_id}:%"}
    for table, statement in _CHECKPOINT_DELETES:
        if await session.scalar(text("SELECT to_regclass(:table)"), {"table": table}):
            await session.execute(text(statement), params)

    # Learning state, then account credit.
    for statement in (
        "DELETE FROM responses WHERE user_id = :user_id",
        "DELETE FROM review_log WHERE user_id = :user_id",
        "DELETE FROM user_sense_stats WHERE user_id = :user_id",
        "DELETE FROM user_learning_settings WHERE user_id = :user_id",
        "DELETE FROM session_summaries WHERE user_id = :user_id",
        "DELETE FROM credit_debits WHERE user_id = :user_id",
        "DELETE FROM user_credits WHERE user_id = :user_id",
    ):
        await session.execute(text(statement), params)


    # Delete pointers and membership before the author's nodes. Nodes are removed
    # deepest-first so a forgotten child FK fails loudly instead of cascading away.
    await session.execute(
        text(
            "DELETE FROM deck_senses WHERE node_id IN "
            "(SELECT id FROM nodes WHERE author_id = :user_id)"
        ),
        params,
    )
    await session.execute(
        text(
            "DELETE FROM nodes WHERE type = 'REFERENCE' AND target_node_id IN "
            "(SELECT id FROM nodes WHERE author_id = :user_id)"
        ),
        params,
    )
    for node_id in await _owned_node_order(session, user_id):
        await session.execute(text("DELETE FROM nodes WHERE id = :node_id"), {"node_id": node_id})

    # Fetch the Clerk subject before the row is gone: it is the external handle
    # this deletion must also remove.
    user = await session.get(User, user_id)
    clerk_id = user.clerk_id if user else None

    await _delete_clerk_identity(clerk_id)

    await session.execute(text("DELETE FROM users WHERE id = :user_id"), params)
    await session.commit()

    if clerk_id:
        # Drop the subject -> actor mapping. Without this the cached actor survives
        # for its TTL; downstream owner-scoped queries would still 404 on the dead
        # UUID, so nothing leaks, but the cache would keep answering for an account
        # that no longer exists.
        await evict_mapping(get_redis(), clerk_id)


async def _delete_clerk_identity(clerk_id: str | None) -> None:
    """Remove the external sign-in identity, before the local rows.

    Order matters and is the whole reason this is not inlined. Clerk is the
    sign-in authority: while the subject still exists, the next sign-in would
    just-in-time provision a fresh Pycil account and the learner would appear
    resurrected with an empty library. Deleting the subject first makes that
    impossible — a failure after it leaves rows that no one can reach, which a
    retry can still finish, whereas the reverse order loses data permanently.

    A missing subject (an account that never signed in) and an already-deleted
    subject are both success: deletion is idempotent so a retry converges.
    """
    if not clerk_id:
        return
    if not settings.clerk_secret_key:
        # Without a credential the external identity cannot be removed, and
        # proceeding would strand a subject that can recreate this account.
        raise ServiceUnavailableError("clerk_not_configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.delete(
            f"https://api.clerk.com/v1/users/{clerk_id}",
            headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
        )
    # 404 means it is already gone, which is the state we wanted.
    if response.status_code not in (200, 204, 404):
        # The body can carry account details, so only the status is surfaced.
        raise ServiceUnavailableError("clerk_deletion_failed")
