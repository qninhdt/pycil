"""Admin audit-log viewer (read-only). Writes go through admin_audit_service.

Gated by AdminDep, mounted under /admin-api/audit. Split out of the former
me_extras junk-drawer; path + AdminDep preserved.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared.db import AdminAction
from sqlmodel import select

from pycil_core.api.deps import AdminDep, SessionDep

router = APIRouter(tags=["admin-audit"])


@router.get("/admin-api/audit")
async def list_audit(
    admin: AdminDep,
    session: SessionDep,
    limit: int = 100,
    cursor: int | None = None,
    action: str | None = None,
    actor: UUID | None = None,
    target: UUID | None = None,
):
    stmt = select(
        AdminAction.id,
        AdminAction.actor_user_id,
        AdminAction.target_user_id,
        AdminAction.action,
        AdminAction.metadata_json.label("metadata"),
        AdminAction.created_at,
        AdminAction.ip_address,
    )
    if cursor is not None:
        stmt = stmt.where(AdminAction.id < cursor)
    if action:
        stmt = stmt.where(AdminAction.action == action)
    if actor is not None:
        stmt = stmt.where(AdminAction.actor_user_id == actor)
    if target is not None:
        stmt = stmt.where(AdminAction.target_user_id == target)
    capped = min(max(limit, 1), 500)
    stmt = stmt.order_by(AdminAction.id.desc()).limit(capped + 1)
    rows = (await session.exec(stmt)).all()
    next_cursor = None
    if len(rows) > capped:
        rows = rows[:capped]
        next_cursor = int(rows[-1].id)
    return {
        "actions": [dict(r._mapping) for r in rows],
        "next_cursor": next_cursor,
    }
