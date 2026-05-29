"""Admin audit log writer (P12 phase 2).

Append-only ledger of every privileged admin operation. Read by
admin UI to render "recent actions" and by GDPR-export to surface
account changes in user data dump.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from shared.db import AdminAction
from sqlmodel.ext.asyncio.session import AsyncSession


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
    record = AdminAction(
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        action=action,
        metadata_json=json.loads(json.dumps(metadata or {}, default=str)),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(record)
    await session.flush()
    return int(record.id or 0)
