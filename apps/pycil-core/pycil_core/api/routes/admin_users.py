"""Admin user-management routes (Phase 2), gated by `AdminDep`.

All routes mount under `/admin-api/*`. Every write records an `admin_actions`
row in the SAME transaction as the mutation (caller-owned txn — red-team F7).

Guards (red-team F14):
- self-ban forbidden,
- banning/revoking an `admin` account forbidden (demote-first),
- last active admin cannot be banned/revoked.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from pycil_core.api.deps import AdminDep, RedisDep, SessionDep
from pycil_core.middleware.rate_limit import enforce
from pycil_core.services import (
    admin_audit_service,
    admin_user_query_service,
    content_report_service,
    user_service,
    user_spend_service,
)

router = APIRouter(prefix="/admin-api/users", tags=["admin-users"])


class BanBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(..., min_length=1, max_length=500)


def _client_ip(request: Request) -> str | None:
    xri = request.headers.get("x-real-ip")
    if xri:
        return xri
    return request.client.host if request.client else None


@router.get("")
async def list_users(
    admin: AdminDep,
    session: SessionDep,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    users = await admin_user_query_service.search_users(
        session, q=q, limit=min(max(limit, 1), 200), offset=max(offset, 0)
    )
    return {"users": users}


@router.get("/{user_id}")
async def user_detail(
    user_id: UUID,
    admin: AdminDep,
    session: SessionDep,
    redis: RedisDep,
) -> dict:
    summary = await admin_user_query_service.get_user_summary(session, user_id=user_id)
    if summary is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    spend_today = await user_spend_service.get_user_spend_today(redis, user_id)
    jobs = await admin_user_query_service.recent_jobs(session, user_id=user_id)
    mastery = await admin_user_query_service.mastery_distribution(session, user_id=user_id)
    reports_against = await content_report_service.count_reports_against(
        session, owner_id=user_id
    )
    return {
        "user": summary,
        "spend_today_usd": round(spend_today, 4),
        "recent_jobs": jobs,
        "mastery_distribution": mastery,
        "reports_against": reports_against,
    }


async def _guard_admin_target(
    session, *, actor_id: UUID, target_id: UUID
) -> None:
    """Block self-action, admin-on-admin, and dropping below one active admin."""
    if target_id == actor_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot_target_self")
    role = await user_service.get_role(session, user_id=target_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    if role == "admin":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "cannot_target_admin_demote_first"
        )


@router.post("/{user_id}/ban")
async def ban_user(
    user_id: UUID,
    body: BanBody,
    admin: AdminDep,
    session: SessionDep,
    request: Request,
) -> dict:
    await enforce(_client_ip(request) or "unknown", "admin_write")
    await _guard_admin_target(session, actor_id=admin.id, target_id=user_id)
    banned = await user_service.set_ban(
        session, user_id=user_id, reason=body.reason
    )
    if not banned:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    await admin_audit_service.record(
        session,
        actor_user_id=admin.id,
        action="ban_user",
        target_user_id=user_id,
        metadata={"reason": body.reason},
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return {"banned": True, "user_id": str(user_id)}


@router.post("/{user_id}/unban")
async def unban_user(
    user_id: UUID,
    admin: AdminDep,
    session: SessionDep,
    request: Request,
) -> dict:
    await enforce(_client_ip(request) or "unknown", "admin_write")
    role = await user_service.get_role(session, user_id=user_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    cleared = await user_service.clear_ban(session, user_id=user_id)
    if not cleared:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    await admin_audit_service.record(
        session,
        actor_user_id=admin.id,
        action="unban_user",
        target_user_id=user_id,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return {"banned": False, "user_id": str(user_id)}


@router.post("/{user_id}/revoke-tokens")
async def revoke_tokens(
    user_id: UUID,
    admin: AdminDep,
    session: SessionDep,
    request: Request,
) -> dict:
    await enforce(_client_ip(request) or "unknown", "admin_write")
    await _guard_admin_target(session, actor_id=admin.id, target_id=user_id)
    try:
        new_tv = await user_service.bump_token_version(session, user_id=user_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found") from exc
    await admin_audit_service.record(
        session,
        actor_user_id=admin.id,
        action="revoke_tokens",
        target_user_id=user_id,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return {"user_id": str(user_id), "token_version": new_tv}
