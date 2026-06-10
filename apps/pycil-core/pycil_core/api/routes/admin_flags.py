"""Admin feature-flag CRUD routes (Phase 6), gated by `AdminDep`.

Every write is single-transaction: flag mutation + cache invalidation + audit
row commit together (red-team F7). Mounts under `/admin-api/flags`.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from pycil_core.api.deps import AdminDep, SessionDep
from pycil_core.middleware.rate_limit import enforce
from pycil_core.services import admin_audit_service, feature_flag_service

router = APIRouter(prefix="/admin-api/flags", tags=["admin-flags"])


class CreateFlagBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=100)
    rollout_percentage: int = Field(default=0, ge=0, le=100)
    enabled_user_ids: list[UUID] = Field(default_factory=list)
    payload: dict = Field(default_factory=dict)


class UpdateFlagBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rollout_percentage: int | None = Field(default=None, ge=0, le=100)
    enabled_user_ids: list[UUID] | None = None
    payload: dict | None = None


def _client_ip(request: Request) -> str | None:
    xri = request.headers.get("x-real-ip")
    if xri:
        return xri
    return request.client.host if request.client else None


@router.get("")
async def list_flags(admin: AdminDep, session: SessionDep) -> dict:
    return {"flags": await feature_flag_service.list_all(session)}


@router.post("")
async def create_flag(
    body: CreateFlagBody,
    admin: AdminDep,
    session: SessionDep,
    request: Request,
) -> dict:
    await enforce(_client_ip(request) or "unknown", "admin_write")
    await feature_flag_service.create(
        session,
        name=body.name,
        rollout_percentage=body.rollout_percentage,
        enabled_user_ids=body.enabled_user_ids,
        payload=body.payload,
        updated_by=admin.id,
    )
    await admin_audit_service.record(
        session,
        actor_user_id=admin.id,
        action="create_flag",
        metadata={"name": body.name, "rollout_percentage": body.rollout_percentage},
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return {"name": body.name, "created": True}


@router.patch("/{name}")
async def update_flag(
    name: str,
    body: UpdateFlagBody,
    admin: AdminDep,
    session: SessionDep,
    request: Request,
) -> dict:
    await enforce(_client_ip(request) or "unknown", "admin_write")
    await feature_flag_service.update_flag(
        session,
        name=name,
        rollout_percentage=body.rollout_percentage,
        enabled_user_ids=body.enabled_user_ids,
        payload=body.payload,
        updated_by=admin.id,
    )
    await admin_audit_service.record(
        session,
        actor_user_id=admin.id,
        action="update_flag",
        metadata={
            "name": name,
            "rollout_percentage": body.rollout_percentage,
        },
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return {"name": name, "updated": True}


@router.delete("/{name}")
async def delete_flag(
    name: str,
    admin: AdminDep,
    session: SessionDep,
    request: Request,
) -> dict:
    await enforce(_client_ip(request) or "unknown", "admin_write")
    await feature_flag_service.delete_flag(session, name=name)
    await admin_audit_service.record(
        session,
        actor_user_id=admin.id,
        action="delete_flag",
        metadata={"name": name},
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return {"name": name, "deleted": True}
