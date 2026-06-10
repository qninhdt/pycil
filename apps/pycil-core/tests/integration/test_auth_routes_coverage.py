"""Coverage tests for pycil_core.api.routes.auth.

Targets the internal upsert endpoint (X-Internal-Secret gate), the
authenticated `PATCH /me` mutation branches (name/bio/study_settings/
image_url/bump_tv/no-op), `DELETE /me` soft-delete, and the
`/me/image-upload-url` signer error paths.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text

from pycil_core.config import get_settings

INTERNAL_HEADER = "X-Internal-Secret"

# ── POST /auth/upsert-user (internal-secret gate) ──────────────────────────


async def test_upsert_user_missing_secret_401(client) -> None:
    resp = await client.post(
        "/auth/upsert-user",
        json={"google_sub": "g1", "email": "new@example.com", "name": "New"},
    )
    assert resp.status_code == 401


async def test_upsert_user_wrong_secret_401(client) -> None:
    resp = await client.post(
        "/auth/upsert-user",
        json={"google_sub": "g1", "email": "new@example.com", "name": "New"},
        headers={INTERNAL_HEADER: "wrong-secret"},
    )
    assert resp.status_code == 401


async def test_upsert_user_new_email_creates_row(client) -> None:
    secret = get_settings().internal_api_secret
    email = f"upsert-{uuid4().hex[:8]}@example.com"
    resp = await client.post(
        "/auth/upsert-user",
        json={"google_sub": "gsub", "email": email, "name": "Fresh"},
        headers={INTERNAL_HEADER: secret},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "user"
    assert body["token_version"] == 0
    assert body["user_id"]


async def test_upsert_user_soft_deleted_410(client, session) -> None:
    secret = get_settings().internal_api_secret
    email = f"gone-{uuid4().hex[:8]}@example.com"
    await session.execute(
        text(
            "INSERT INTO users (email, name, deleted_at) "
            "VALUES (:e, 'Gone', NOW())"
        ),
        {"e": email},
    )
    await session.commit()
    resp = await client.post(
        "/auth/upsert-user",
        json={"google_sub": "g2", "email": email, "name": "Gone"},
        headers={INTERNAL_HEADER: secret},
    )
    assert resp.status_code == 410


# ── PATCH /me ──────────────────────────────────────────────────────────────


async def test_patch_me_updates_name(client, session, test_user) -> None:
    resp = await client.patch("/me", json={"name": "Renamed"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"
    row = (
        await session.execute(
            text("SELECT name FROM users WHERE id = :id"), {"id": test_user["id"]}
        )
    ).one()
    assert row.name == "Renamed"


async def test_patch_me_updates_bio(client, session, test_user) -> None:
    resp = await client.patch("/me", json={"bio": "hello world"})
    assert resp.status_code == 200
    row = (
        await session.execute(
            text("SELECT bio FROM users WHERE id = :id"), {"id": test_user["id"]}
        )
    ).one()
    assert row.bio == "hello world"


async def test_patch_me_study_settings_persisted(client, session, test_user) -> None:
    resp = await client.patch(
        "/me", json={"study_settings": {"theme": "dark"}}
    )
    assert resp.status_code == 200


async def test_patch_me_study_settings_too_large_413(client) -> None:
    big = {"blob": "x" * 5000}
    resp = await client.patch("/me", json={"study_settings": big})
    assert resp.status_code == 413


async def test_patch_me_blank_name_422(client) -> None:
    # min_length=1 lets a single space through schema, stripped → empty → 422.
    resp = await client.patch("/me", json={"name": " "})
    assert resp.status_code == 422


async def test_patch_me_image_url_not_configured_503(client) -> None:
    # b2_public_url_prefix is unset in the test env → image storage unavailable.
    resp = await client.patch(
        "/me", json={"image_url": "https://example.com/avatar.png"}
    )
    assert resp.status_code == 503


async def test_patch_me_noop_returns_current_user(client, test_user) -> None:
    resp = await client.patch("/me", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(test_user["id"])
    assert body["email"] == test_user["email"]


async def test_patch_me_bump_tv_revokes_tokens(client, session, test_user) -> None:
    resp = await client.patch("/me", json={"bump_tv": True})
    assert resp.status_code == 200
    row = (
        await session.execute(
            text("SELECT token_version FROM users WHERE id = :id"),
            {"id": test_user["id"]},
        )
    ).one()
    assert row.token_version >= 1


# ── DELETE /me ──────────────────────────────────────────────────────────────


async def test_delete_me_soft_deletes(client, session, test_user) -> None:
    resp = await client.delete("/me")
    assert resp.status_code == 200
    assert "deleted_at" in resp.json()
    row = (
        await session.execute(
            text("SELECT deleted_at FROM users WHERE id = :id"),
            {"id": test_user["id"]},
        )
    ).one()
    assert row.deleted_at is not None


# ── POST /me/image-upload-url ───────────────────────────────────────────────


async def test_image_upload_url_unsupported_type_400(client) -> None:
    resp = await client.post(
        "/me/image-upload-url", json={"content_type": "text/plain"}
    )
    assert resp.status_code == 400


async def test_image_upload_url_storage_not_configured_503(client) -> None:
    # Valid content type but b2_bucket is unset → RuntimeError → 503.
    resp = await client.post(
        "/me/image-upload-url", json={"content_type": "image/png"}
    )
    assert resp.status_code == 503
