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
from sqlalchemy import text

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.config import get_settings
from pycil_core.services import image_upload_service, user_service


router = APIRouter(tags=["auth"])


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
    bio: str | None = Field(default=None, max_length=500)
    study_settings: dict | None = None
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
    """Reject anything not under the configured B2 public URL prefix.

    Uses full host + path-prefix match via urlparse to defeat
    `https://attacker.com/?fake=https://b2.../...` style bypasses that
    a naive `startswith` would accept.
    """
    from urllib.parse import urlparse

    settings = get_settings()
    prefix = getattr(settings, "b2_public_url_prefix", None)
    if not prefix:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "image_storage_not_configured"
        )
    expected = urlparse(prefix.rstrip("/"))
    actual = urlparse(url)
    if (
        actual.scheme != expected.scheme
        or actual.netloc != expected.netloc
        or not actual.path.startswith(expected.path + "/")
    ):
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
    import json as _json

    if body.image_url is not None:
        _validate_image_url(body.image_url)

    settings_json: str | None = None
    if body.study_settings is not None:
        settings_json = _json.dumps(body.study_settings)
        if len(settings_json) > 4096:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "study_settings_too_large"
            )

    name_value = body.name.strip() if body.name is not None else None
    if name_value is not None and not name_value:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "name_empty")

    set_clauses: list[str] = []
    params: dict = {"uid": user.id}
    if name_value is not None:
        set_clauses.append("name = :name")
        params["name"] = name_value
    if body.image_url is not None:
        set_clauses.append("image_url = :image_url")
        params["image_url"] = body.image_url
    if body.bio is not None:
        set_clauses.append("bio = :bio")
        params["bio"] = body.bio
    if settings_json is not None:
        set_clauses.append("study_settings = CAST(:settings AS jsonb)")
        params["settings"] = settings_json

    try:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('user-mutate:' || CAST(:uid AS text)))"),
            {"uid": user.id},
        )
        if set_clauses:
            set_clauses.append("updated_at = NOW()")
            sql = (
                "UPDATE users SET " + ", ".join(set_clauses)
                + " WHERE id = :uid RETURNING id, email, name, image, image_url"
            )
            row = (await session.execute(text(sql), params)).first()
            if row is None:
                await session.rollback()
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "user_not_found_yet"
                )
            updated = {
                "id": row.id,
                "email": row.email,
                "name": row.name,
                "image": row.image,
                "image_url": row.image_url,
            }
        else:
            updated = {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "image": user.image,
                "image_url": None,
            }
        if body.bump_tv:
            await user_service.revoke_tokens(session, user_id=user.id)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except LookupError:
        await session.rollback()
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


class ImageUploadUrlBody(BaseModel):
    content_type: str


@router.post("/me/image-upload-url")
async def image_upload_url(body: ImageUploadUrlBody, user: UserDep) -> dict:
    """Return a signed PUT URL bound to a server-generated key."""
    try:
        return await image_upload_service.generate_put_url(
            user_id=user.id, content_type=body.content_type
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

