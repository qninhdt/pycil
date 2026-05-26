"""Admin audit log writer (P12 phase 2).

Append-only ledger of every privileged admin operation. Read by
admin UI to render "recent actions" and by GDPR-export to surface
account changes in user data dump.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def record(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    action: str,
    target_user_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> int:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO admin_actions
                  (actor_user_id, target_user_id, action, metadata,
                   ip_address, user_agent)
                VALUES (:actor, :target, :action, CAST(:meta AS jsonb),
                        :ip::inet, :ua)
                RETURNING id
                """
            ),
            {
                "actor": actor_user_id,
                "target": target_user_id,
                "action": action,
                "meta": _json_dumps(metadata or {}),
                "ip": ip_address,
                "ua": user_agent,
            },
        )
    ).one()
    return int(row.id)


def _json_dumps(d: dict[str, Any]) -> str:
    import json
    return json.dumps(d, default=str)
