"""Phase 1 RBAC foundation tests.

Covers the load-bearing admin gate:
- `require_admin` returns 403 for non-admins, 200 for admins.
- Banned users get 403 `account_banned` on every authenticated request.
- `CurrentUser` exposes `role` read from the DB.
- PATCH `/me` cannot set `role`/`banned_at`/`token_version` (extra="forbid").
- `/auth/upsert-user` returns `role` + `token_version` for the edge JWT claim.

`signed_cookie` and `admin_client` fixtures live in conftest.py.
"""
from __future__ import annotations

from uuid import uuid4

from pycil_core.config import get_settings

# ── require_admin gate ──────────────────────────────────────────────────────


async def test_non_admin_gets_403_on_admin_route(client) -> None:
    """The default `client` fixture user has role=user → 403."""
    resp = await client.get("/admin-api/ping")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "admin_required"


async def test_admin_gets_200_on_admin_route(admin_client) -> None:
    resp = await admin_client.get("/admin-api/ping")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ── banned lockout (real auth path) ─────────────────────────────────────────


async def test_banned_user_gets_403_account_banned(
    client_real_auth, session, signed_cookie
) -> None:
    from sqlalchemy import text

    email = f"pytest-banned-{uuid4().hex[:8]}@example.test"
    row = (
        await session.execute(
            text(
                "INSERT INTO users (email, name, banned_at, ban_reason) "
                "VALUES (:e, :n, NOW(), 'spam') RETURNING id"
            ),
            {"e": email, "n": "BannedUser"},
        )
    ).one()
    await session.commit()

    cookie = signed_cookie(row.id)
    resp = await client_real_auth.get(
        "/me", cookies={get_settings().session_cookie_name: cookie}
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "account_banned"


async def test_current_user_exposes_role_from_db(
    client_real_auth, admin_user, signed_cookie
) -> None:
    """A fresh request reads role from DB → admin route reachable via real auth."""
    cookie = signed_cookie(admin_user["id"])
    resp = await client_real_auth.get(
        "/admin-api/ping", cookies={get_settings().session_cookie_name: cookie}
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ── PATCH /me mass-assignment guard ─────────────────────────────────────────


async def test_patch_me_rejects_role_field(client) -> None:
    resp = await client.patch("/me", json={"role": "admin"})
    assert resp.status_code == 422


async def test_patch_me_rejects_banned_at_and_token_version(client) -> None:
    for field, value in (
        ("banned_at", "2026-01-01T00:00:00Z"),
        ("token_version", 99),
    ):
        resp = await client.patch("/me", json={field: value})
        assert resp.status_code == 422, f"{field} should be rejected"


# ── upsert-user returns role + token_version (edge claim source) ────────────


async def test_upsert_user_returns_role_and_token_version(
    client_real_auth,
) -> None:
    email = f"pytest-upsert-{uuid4().hex[:8]}@example.com"
    resp = await client_real_auth.post(
        "/auth/upsert-user",
        json={"google_sub": "g-123", "email": email, "name": "Upserted"},
        headers={"x-internal-secret": get_settings().internal_api_secret},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "user_id" in body
    assert body["role"] == "user"
    assert body["token_version"] == 0
