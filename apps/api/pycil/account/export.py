"""Account data export service."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.billing.ledger import get_usage_allowance
from pycil.platform.errors import NotFoundError


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
    allowance = await get_usage_allowance(session, user_id)

    return {
        "profile": profile,
        "collection": [
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
        "plan": allowance.plan,
        "usage": allowance.as_dict(),
        "credit": allowance.as_dict(),
        "periods": await _rows(
            session,
            "SELECT id, user_id, plan_key, period_start, period_end, allowance_units, used_units, "
            "created_at, updated_at FROM usage_periods "
            "WHERE user_id = :user_id ORDER BY period_start ASC",
            {"user_id": user_id},
        ),
        "usage_events": await _rows(
            session,
            "SELECT e.id, e.period_id, e.event_key, e.feature_key, e.units, e.occurred_at, "
            "e.details, e.created_at FROM usage_events e "
            "JOIN usage_periods p ON p.id = e.period_id "
            "WHERE p.user_id = :user_id ORDER BY e.created_at ASC",
            {"user_id": user_id},
        ),
    }
