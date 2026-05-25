"""Internal-only auth endpoints + authenticated `PATCH /me`, `DELETE /me`.

`POST /auth/upsert-user` is called by Next.js Auth.js `signIn` callback
over the docker-internal network and authenticated by the
`X-Internal-Secret` header. It MUST NOT be reachable through Caddy's
public `/api/core/*` route — phase 10 adds an explicit 404 block.

`PATCH /me` accepts name/image_url/bump_tv. `DELETE /me` soft-deletes
the account; cron purges after 14d.
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.config import get_settings
from pycil_core.services import user_service


router = APIRouter(tags=["auth"])

_B2_PUBLIC_PREFIX_PLACEHOLDER = "https://"


class UpsertUserBody(BaseModel):
    google_sub: str
    email: EmailStr
    name: str | None = None
    image: str | None = None


class UpsertUserResponse(BaseModel):
    user_id: str


class UpdateMeBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    image_url: str | None = None
    bump_tv: bool = False


class MeResponse(BaseModel):
    id: str
    email: str
    name: str | None = None
    image: str | None = None
    image_url: str | None = None


class DeleteMeResponse(BaseModel):
    deleted_at: str


def _verify_internal_secret(provided: str | None) -> None:
    expected = get_settings().internal_api_secret
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_internal_secret")


def _validate_image_url(url: str) -> None:
    settings = get_settings()
    prefix = getattr(settings, "b2_public_url_prefix", None) or _B2_PUBLIC_PREFIX_PLACEHOLDER
    if not url.startswith(prefix):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "image_url_not_in_bucket"
        )


@router.post("/auth/upsert-user", response_model=UpsertUserResponse)
async def upsert_user(
    body: UpsertUserBody,
    session: SessionDep,
    x_internal_secret: str | None = Header(default=None, alias="X-Internal-Secret"),
) -> UpsertUserResponse:
    _verify_internal_secret(x_internal_secret)
    if await user_service.is_soft_deleted(session, email=body.email):
        raise HTTPException(status.HTTP_410_GONE, "account_deleted")
    user_id = await user_service.upsert_user(
        session,
        email=body.email,
        name=body.name,
        image=body.image,
    )
    return UpsertUserResponse(user_id=str(user_id))


@router.patch("/me", response_model=MeResponse)
async def update_me(
    body: UpdateMeBody, user: UserDep, session: SessionDep
) -> MeResponse:
    updated: dict = {"id": user.id, "email": user.email, "name": user.name, "image": user.image, "image_url": None}
    try:
        if body.name is not None:
            updated = await user_service.update_user_name(
                session, user_id=user.id, name=body.name
            )
        if body.image_url is not None:
            _validate_image_url(body.image_url)
            updated = await user_service.update_image_url(
                session, user_id=user.id, image_url=body.image_url
            )
        if body.bump_tv:
            await user_service.revoke_tokens(session, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    return MeResponse(
        id=str(updated["id"]),
        email=updated["email"],
        name=updated.get("name"),
        image=updated.get("image"),
        image_url=updated.get("image_url"),
    )


@router.delete("/me", response_model=DeleteMeResponse)
async def delete_me(user: UserDep, session: SessionDep) -> DeleteMeResponse:
    """Soft-delete the calling user. Cron hard-deletes after 14d."""
    await user_service.soft_delete_user(session, user_id=user.id)
    from datetime import datetime, timezone
    return DeleteMeResponse(deleted_at=datetime.now(timezone.utc).isoformat())

