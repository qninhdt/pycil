"""Account lifecycle deletion service."""

from uuid import UUID

from clerk_backend_api.models import ClerkBaseError, ClerkErrors
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.auth import evict_mapping
from pycil.account.user import User
from pycil.platform.clerk import get_clerk_client
from pycil.platform.errors import NotFoundError, ServiceUnavailableError
from pycil.platform.redis import get_redis
from pycil.platform.settings import settings  # noqa: F401

_CHECKPOINT_DELETES = (
    ("checkpoint_writes", "DELETE FROM checkpoint_writes WHERE thread_id LIKE :checkpoint_prefix"),
    ("checkpoint_blobs", "DELETE FROM checkpoint_blobs WHERE thread_id LIKE :checkpoint_prefix"),
    ("checkpoints", "DELETE FROM checkpoints WHERE thread_id LIKE :checkpoint_prefix"),
)


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
    """Delete one account in explicit owner order.

    The external Clerk identity is removed *before* the local rows transaction,
    preventing DB locks across external HTTP requests and preventing account resurrection.
    Billing data (AccountPlan, UsagePeriod, UsageEvent) cascades automatically
    when the User row is deleted.
    """
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("account_not_found")
    clerk_id = user.clerk_id

    # 1. External Clerk deletion prior to DB transaction
    await _delete_clerk_identity(clerk_id)

    # 2. Assistant threads and checkpoints
    await session.execute(
        text("DELETE FROM assistant_threads WHERE owner_id = :user_id"), {"user_id": user_id}
    )
    params = {"user_id": user_id, "checkpoint_prefix": f"assistant:{user_id}:%"}
    for table, statement in _CHECKPOINT_DELETES:
        if await session.scalar(text("SELECT to_regclass(:table)"), {"table": table}):
            await session.execute(text(statement), params)

    # 3. Learning state
    for statement in (
        "DELETE FROM responses WHERE user_id = :user_id",
        "DELETE FROM review_log WHERE user_id = :user_id",
        "DELETE FROM user_sense_stats WHERE user_id = :user_id",
        "DELETE FROM user_learning_settings WHERE user_id = :user_id",
        "DELETE FROM session_summaries WHERE user_id = :user_id",
    ):
        await session.execute(text(statement), params)

    # 4. Content hierarchy
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

    # 5. Delete user (cascades account_plans, usage_periods, usage_events)
    await session.execute(text("DELETE FROM users WHERE id = :user_id"), params)
    await session.commit()

    # 6. Evict cached mapping
    if clerk_id:
        await evict_mapping(get_redis(), clerk_id)


async def _delete_clerk_identity(clerk_id: str | None) -> None:
    """Remove the external sign-in identity."""
    if not clerk_id:
        return
    clerk = get_clerk_client()
    try:
        await clerk.users.delete_async(user_id=clerk_id)
    except ClerkErrors as exc:
        if exc.status_code == 404:
            return
        raise ServiceUnavailableError("clerk_deletion_failed") from exc
    except ClerkBaseError as exc:
        if getattr(exc, "status_code", None) == 404:
            return
        raise ServiceUnavailableError("clerk_deletion_failed") from exc
    except Exception as exc:
        raise ServiceUnavailableError("clerk_deletion_failed") from exc
