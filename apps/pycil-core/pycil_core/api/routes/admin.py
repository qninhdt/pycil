"""Admin-only operations gated by X-Internal-Secret header.

Mounted at /admin/* (NOT /api/core/admin/*) and blocked at the Caddy layer
via `respond /api/core/admin/* 404`. Same secret as Auth.js callback.
"""
from __future__ import annotations

import hmac
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status

from pycil_core.api.deps import SessionDep
from pycil_core.config import get_settings
from pycil_core.services import user_service

router = APIRouter(prefix="/admin", tags=["admin"])


def _verify(provided: str | None) -> None:
    expected = get_settings().internal_api_secret
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_internal_secret")


@router.post("/users/{user_id}/revoke-tokens")
async def revoke_tokens(
    user_id: UUID,
    session: SessionDep,
    x_internal_secret: str | None = Header(default=None, alias="X-Internal-Secret"),
) -> dict:
    _verify(x_internal_secret)
    try:
        new_tv = await user_service.revoke_tokens(session, user_id=user_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found") from exc
    return {"user_id": str(user_id), "token_version": new_tv}
