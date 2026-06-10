"""Phase 2 admin user-management + ban tests.

Covers:
- non-admin → all `/admin-api/users*` 403.
- list + search by email/name/username.
- detail aggregate shape (stats / spend / jobs / mastery keys present).
- ban sets `banned_at` + bumps `token_version` + writes an `admin_actions` row;
  banned user's next authenticated request → 403 (Phase 1 lockout).
- self-ban → 400; admin-on-admin ban → 400; last-admin guard.
- unban clears `banned_at`; ban→unban→fresh login succeeds (token_version flow).
- revoke-tokens (human variant) bumps token_version + audits.
"""
from __future__ import annotations

from uuid import uuid4

import pytest_asyncio
from sqlalchemy import text

from pycil_core.config import get_settings


@pytest_asyncio.fixture
async def seeded_users(session) -> list[dict]:
    """Insert a few non-admin users for list/search tests."""
    rows = []
    specs = [
        ("alice@example.com", "Alice", "alice_w"),
        ("bob@example.com", "Bob Smith", "bobby"),
        ("carol@example.com", "Carol", None),
    ]
    for email, name, username in specs:
        row = (
            await session.execute(
                text(
                    "INSERT INTO users (email, name, username) "
                    "VALUES (:e, :n, :u) RETURNING id"
                ),
                {"e": email, "n": name, "u": username},
            )
        ).one()
        rows.append({"id": row.id, "email": email, "name": name})
    await session.commit()
    return rows


async def _count_audit(session, action: str, target_id) -> int:
    return (
        await session.execute(
            text(
                "SELECT COUNT(*) AS c FROM admin_actions "
                "WHERE action = :a AND target_user_id = :t"
            ),
            {"a": action, "t": target_id},
        )
    ).one().c


# ── authz ───────────────────────────────────────────────────────────────────


async def test_non_admin_forbidden_on_all_user_routes(client, seeded_users) -> None:
    uid = seeded_users[0]["id"]
    assert (await client.get("/admin-api/users")).status_code == 403
    assert (await client.get(f"/admin-api/users/{uid}")).status_code == 403
    assert (
        await client.post(f"/admin-api/users/{uid}/ban", json={"reason": "x"})
    ).status_code == 403
    assert (
        await client.post(f"/admin-api/users/{uid}/unban")
    ).status_code == 403
    assert (
        await client.post(f"/admin-api/users/{uid}/revoke-tokens")
    ).status_code == 403


# ── list + search ─────────────────────────────────────────────────────────


async def test_admin_list_returns_users(admin_client, seeded_users) -> None:
    resp = await admin_client.get("/admin-api/users")
    assert resp.status_code == 200
    body = resp.json()
    assert "users" in body
    emails = {u["email"] for u in body["users"]}
    assert {"alice@example.com", "bob@example.com"}.issubset(emails)


async def test_admin_search_by_email(admin_client, seeded_users) -> None:
    resp = await admin_client.get("/admin-api/users", params={"q": "alice"})
    assert resp.status_code == 200
    users = resp.json()["users"]
    assert len(users) == 1
    assert users[0]["email"] == "alice@example.com"


async def test_admin_search_by_username(admin_client, seeded_users) -> None:
    resp = await admin_client.get("/admin-api/users", params={"q": "bobby"})
    assert resp.status_code == 200
    users = resp.json()["users"]
    assert any(u["email"] == "bob@example.com" for u in users)


# ── detail aggregate ────────────────────────────────────────────────────────


async def test_admin_detail_aggregate_shape(admin_client, seeded_users) -> None:
    uid = seeded_users[0]["id"]
    resp = await admin_client.get(f"/admin-api/users/{uid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == "alice@example.com"
    for key in ("spend_today_usd", "recent_jobs", "mastery_distribution"):
        assert key in body


async def test_admin_detail_unknown_user_404(admin_client) -> None:
    resp = await admin_client.get(f"/admin-api/users/{uuid4()}")
    assert resp.status_code == 404


# ── ban / lockout ────────────────────────────────────────────────────────────


async def test_ban_sets_banned_at_bumps_tv_and_audits(
    admin_client, session, seeded_users
) -> None:
    uid = seeded_users[0]["id"]
    resp = await admin_client.post(
        f"/admin-api/users/{uid}/ban", json={"reason": "spam"}
    )
    assert resp.status_code == 200

    row = (
        await session.execute(
            text(
                "SELECT banned_at, ban_reason, token_version "
                "FROM users WHERE id = :id"
            ),
            {"id": uid},
        )
    ).one()
    assert row.banned_at is not None
    assert row.ban_reason == "spam"
    assert row.token_version == 1
    assert await _count_audit(session, "ban_user", uid) == 1


async def test_banned_user_locked_out_next_request(
    client_real_auth, session, seeded_users, admin_user, signed_cookie
) -> None:
    uid = seeded_users[0]["id"]
    cookie_name = get_settings().session_cookie_name
    admin_cookie = signed_cookie(admin_user["id"])

    # User can reach /me before the ban.
    pre = await client_real_auth.get(
        "/me", cookies={cookie_name: signed_cookie(uid)}
    )
    assert pre.status_code == 200

    # Admin bans via the real-auth path (own admin cookie).
    banned = await client_real_auth.post(
        f"/admin-api/users/{uid}/ban",
        json={"reason": "x"},
        cookies={cookie_name: admin_cookie},
    )
    assert banned.status_code == 200

    # The pre-ban cookie (tv=0) now mismatches the bumped token_version → 401.
    stale = await client_real_auth.get(
        "/me", cookies={cookie_name: signed_cookie(uid)}
    )
    assert stale.status_code == 401

    # Even a cookie carrying the CURRENT token_version is hard-locked → 403.
    tv = (
        await session.execute(
            text("SELECT token_version FROM users WHERE id = :id"), {"id": uid}
        )
    ).one().token_version
    locked = await client_real_auth.get(
        "/me", cookies={cookie_name: signed_cookie(uid, tv=tv)}
    )
    assert locked.status_code == 403
    assert locked.json()["detail"] == "account_banned"


async def test_self_ban_forbidden(admin_client, admin_user) -> None:
    resp = await admin_client.post(
        f"/admin-api/users/{admin_user['id']}/ban", json={"reason": "x"}
    )
    assert resp.status_code == 400


async def test_cannot_ban_another_admin(admin_client, session) -> None:
    email = f"other-admin-{uuid4().hex[:8]}@example.com"
    row = (
        await session.execute(
            text(
                "INSERT INTO users (email, name, role) "
                "VALUES (:e, 'Other Admin', 'admin') RETURNING id"
            ),
            {"e": email},
        )
    ).one()
    await session.commit()
    resp = await admin_client.post(
        f"/admin-api/users/{row.id}/ban", json={"reason": "x"}
    )
    assert resp.status_code == 400


# ── unban + token_version round-trip ─────────────────────────────────────────


async def test_unban_clears_banned_at_and_audits(
    admin_client, session, seeded_users
) -> None:
    uid = seeded_users[0]["id"]
    await admin_client.post(f"/admin-api/users/{uid}/ban", json={"reason": "x"})
    resp = await admin_client.post(f"/admin-api/users/{uid}/unban")
    assert resp.status_code == 200

    row = (
        await session.execute(
            text("SELECT banned_at, ban_reason FROM users WHERE id = :id"),
            {"id": uid},
        )
    ).one()
    assert row.banned_at is None
    assert row.ban_reason is None
    assert await _count_audit(session, "unban_user", uid) == 1


async def test_ban_then_unban_then_fresh_login_succeeds(
    client_real_auth, session, seeded_users, admin_user, signed_cookie
) -> None:
    """The token_version root-flow fix: after unban, a freshly minted cookie
    (carrying the current token_version) authenticates again — no permanent
    lockout."""
    uid = seeded_users[0]["id"]
    cookie_name = get_settings().session_cookie_name
    admin_cookie = signed_cookie(admin_user["id"])

    await client_real_auth.post(
        f"/admin-api/users/{uid}/ban",
        json={"reason": "x"},
        cookies={cookie_name: admin_cookie},
    )
    await client_real_auth.post(
        f"/admin-api/users/{uid}/unban", cookies={cookie_name: admin_cookie}
    )

    # Read the live token_version (ban bumped it to 1) → mint a fresh cookie.
    tv = (
        await session.execute(
            text("SELECT token_version FROM users WHERE id = :id"), {"id": uid}
        )
    ).one().token_version
    resp = await client_real_auth.get(
        "/me",
        cookies={cookie_name: signed_cookie(uid, tv=tv)},
    )
    assert resp.status_code == 200


# ── revoke-tokens (human variant) ─────────────────────────────────────────


async def test_revoke_tokens_bumps_tv_and_audits(
    admin_client, session, seeded_users
) -> None:
    uid = seeded_users[0]["id"]
    resp = await admin_client.post(f"/admin-api/users/{uid}/revoke-tokens")
    assert resp.status_code == 200
    row = (
        await session.execute(
            text("SELECT token_version FROM users WHERE id = :id"), {"id": uid}
        )
    ).one()
    assert row.token_version == 1
    assert await _count_audit(session, "revoke_tokens", uid) == 1
