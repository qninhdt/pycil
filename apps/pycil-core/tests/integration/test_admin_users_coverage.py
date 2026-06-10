"""Coverage tests for pycil_core.api.routes.admin_users.

Targets the AdminDep 403 gate, list/search pagination clamps, user-detail
aggregate + 404, and the ban/unban/revoke guard branches: self-target 400,
admin-target 400, unknown-user 404, and the happy mutation + audit paths.
"""
from __future__ import annotations

from uuid import uuid4

import pytest_asyncio
from sqlalchemy import text


@pytest_asyncio.fixture
async def plain_user(session) -> dict:
    """A non-admin user to be the target of ban/unban/revoke."""
    email = f"target-{uuid4().hex[:8]}@example.com"
    row = (
        await session.execute(
            text("INSERT INTO users (email, name) VALUES (:e, 'Target') RETURNING id"),
            {"e": email},
        )
    ).one()
    await session.commit()
    return {"id": row.id, "email": email}


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


# ── AdminDep gate ────────────────────────────────────────────────────────────


async def test_non_admin_forbidden(client, plain_user) -> None:
    uid = plain_user["id"]
    assert (await client.get("/admin-api/users")).status_code == 403
    assert (await client.get(f"/admin-api/users/{uid}")).status_code == 403


# ── list + pagination clamps ────────────────────────────────────────────────


async def test_admin_list_default(admin_client, plain_user) -> None:
    resp = await admin_client.get("/admin-api/users")
    assert resp.status_code == 200
    assert "users" in resp.json()


async def test_admin_list_pagination_clamps(admin_client, plain_user) -> None:
    # limit above 200 and a negative offset are clamped server-side, not 422.
    resp = await admin_client.get(
        "/admin-api/users", params={"limit": 9999, "offset": -5}
    )
    assert resp.status_code == 200


async def test_admin_search_query(admin_client, plain_user) -> None:
    resp = await admin_client.get(
        "/admin-api/users", params={"q": plain_user["email"]}
    )
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()["users"]}
    assert plain_user["email"] in emails


# ── user detail ──────────────────────────────────────────────────────────────


async def test_user_detail_aggregate(admin_client, plain_user) -> None:
    resp = await admin_client.get(f"/admin-api/users/{plain_user['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == plain_user["email"]
    for key in (
        "spend_today_usd",
        "recent_jobs",
        "mastery_distribution",
        "reports_against",
    ):
        assert key in body


async def test_user_detail_not_found_404(admin_client) -> None:
    resp = await admin_client.get(f"/admin-api/users/{uuid4()}")
    assert resp.status_code == 404


# ── ban guards + happy path ─────────────────────────────────────────────────


async def test_ban_self_forbidden_400(admin_client, admin_user) -> None:
    resp = await admin_client.post(
        f"/admin-api/users/{admin_user['id']}/ban", json={"reason": "x"}
    )
    assert resp.status_code == 400


async def test_ban_admin_target_forbidden_400(admin_client, session) -> None:
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


async def test_ban_unknown_user_404(admin_client) -> None:
    # _guard_admin_target's get_role returns None for a missing user → 404.
    resp = await admin_client.post(
        f"/admin-api/users/{uuid4()}/ban", json={"reason": "x"}
    )
    assert resp.status_code == 404


async def test_ban_happy_path_audits(admin_client, session, plain_user) -> None:
    uid = plain_user["id"]
    resp = await admin_client.post(
        f"/admin-api/users/{uid}/ban", json={"reason": "spam"}
    )
    assert resp.status_code == 200
    assert resp.json()["banned"] is True
    assert await _count_audit(session, "ban_user", uid) == 1


# ── unban ────────────────────────────────────────────────────────────────────


async def test_unban_unknown_user_404(admin_client) -> None:
    resp = await admin_client.post(f"/admin-api/users/{uuid4()}/unban")
    assert resp.status_code == 404


async def test_unban_happy_path_audits(admin_client, session, plain_user) -> None:
    uid = plain_user["id"]
    await admin_client.post(f"/admin-api/users/{uid}/ban", json={"reason": "x"})
    resp = await admin_client.post(f"/admin-api/users/{uid}/unban")
    assert resp.status_code == 200
    assert resp.json()["banned"] is False
    assert await _count_audit(session, "unban_user", uid) == 1


# ── revoke-tokens ────────────────────────────────────────────────────────────


async def test_revoke_self_forbidden_400(admin_client, admin_user) -> None:
    resp = await admin_client.post(
        f"/admin-api/users/{admin_user['id']}/revoke-tokens"
    )
    assert resp.status_code == 400


async def test_revoke_unknown_user_404(admin_client) -> None:
    resp = await admin_client.post(f"/admin-api/users/{uuid4()}/revoke-tokens")
    assert resp.status_code == 404


async def test_revoke_happy_path_audits(admin_client, session, plain_user) -> None:
    uid = plain_user["id"]
    resp = await admin_client.post(f"/admin-api/users/{uid}/revoke-tokens")
    assert resp.status_code == 200
    assert "token_version" in resp.json()
    assert await _count_audit(session, "revoke_tokens", uid) == 1
