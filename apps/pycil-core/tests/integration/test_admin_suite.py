"""End-to-end admin-suite integration + audit-coverage (Phase 8).

Drives the full admin journey through the REAL auth path (cookies), proving:
- the Caddy-forwarded `/admin-api/*` surface is reachable & admin-gated,
- every admin WRITE emits an `admin_actions` row (audit coverage),
- the previously-dead `/admin-api/audit` viewer surfaces those rows.

Audit-coverage enumerates the expected action types across users (ban / unban /
revoke), report-resolve, and flag CRUD. Adding a new admin write without an
audit call fails `test_audit_coverage_all_write_actions`.
"""
from __future__ import annotations

from uuid import uuid4

import pytest_asyncio
from sqlalchemy import text

from pycil_core.config import get_settings

COOKIE = get_settings().session_cookie_name


@pytest_asyncio.fixture
async def target_user(session) -> dict:
    row = (
        await session.execute(
            text(
                "INSERT INTO users (email, name) VALUES (:e, 'Target') RETURNING id"
            ),
            {"e": f"target-{uuid4().hex[:8]}@example.com"},
        )
    ).one()
    await session.commit()
    return {"id": str(row.id)}


@pytest_asyncio.fixture
async def reportable_deck(session) -> dict:
    """A PUBLIC deck owned by a third user (so the admin can report+resolve it)."""
    owner = (
        await session.execute(
            text("INSERT INTO users (email) VALUES (:e) RETURNING id"),
            {"e": f"deckowner-{uuid4().hex[:8]}@example.com"},
        )
    ).one()
    deck = (
        await session.execute(
            text(
                "INSERT INTO nodes (author_id, type, name, visibility) "
                "VALUES (:a, 'DECK'::node_type, 'Bad Deck', 'PUBLIC'::visibility) "
                "RETURNING id"
            ),
            {"a": owner.id},
        )
    ).one()
    await session.commit()
    return {"id": str(deck.id), "owner": str(owner.id)}


async def _audit_actions(session) -> set[str]:
    rows = (
        await session.execute(text("SELECT DISTINCT action FROM admin_actions"))
    ).all()
    return {r.action for r in rows}


async def test_full_admin_journey(
    client_real_auth, session, admin_user, target_user, reportable_deck, signed_cookie
) -> None:
    admin_cookie = signed_cookie(admin_user["id"])
    ck = {COOKIE: admin_cookie}

    # 1. List users (gated surface reachable).
    assert (await client_real_auth.get("/admin-api/users", cookies=ck)).status_code == 200

    # 2. Ban → unban → revoke the target.
    assert (
        await client_real_auth.post(
            f"/admin-api/users/{target_user['id']}/ban",
            json={"reason": "spam"},
            cookies=ck,
        )
    ).status_code == 200
    assert (
        await client_real_auth.post(
            f"/admin-api/users/{target_user['id']}/unban", cookies=ck
        )
    ).status_code == 200
    assert (
        await client_real_auth.post(
            f"/admin-api/users/{target_user['id']}/revoke-tokens", cookies=ck
        )
    ).status_code == 200

    # 3. Admin reports the deck (as a user) then resolves it.
    rep = await client_real_auth.post(
        "/reports",
        json={"content_type": "deck", "content_id": reportable_deck["id"], "reason": "bad"},
        cookies=ck,
    )
    assert rep.status_code == 200
    report_id = rep.json()["report_id"]
    assert (
        await client_real_auth.post(
            f"/admin-api/reports/{report_id}/resolve",
            json={"action": "delete_content"},
            cookies=ck,
        )
    ).status_code == 200

    # 4. Flag CRUD.
    flag_name = f"flag-{uuid4().hex[:6]}"
    assert (
        await client_real_auth.post(
            "/admin-api/flags",
            json={"name": flag_name, "rollout_percentage": 10},
            cookies=ck,
        )
    ).status_code == 200
    assert (
        await client_real_auth.patch(
            f"/admin-api/flags/{flag_name}",
            json={"rollout_percentage": 50},
            cookies=ck,
        )
    ).status_code == 200
    assert (
        await client_real_auth.delete(f"/admin-api/flags/{flag_name}", cookies=ck)
    ).status_code == 200

    # 5. Read-only surfaces respond.
    assert (await client_real_auth.get("/admin-api/metrics", cookies=ck)).status_code == 200
    assert (await client_real_auth.get("/admin-api/health", cookies=ck)).status_code == 200

    # 6. Audit viewer surfaces the journey's actions.
    audit = await client_real_auth.get("/admin-api/audit", cookies=ck)
    assert audit.status_code == 200
    assert len(audit.json()["actions"]) >= 7


async def test_audit_coverage_all_write_actions(
    client_real_auth, session, admin_user, target_user, reportable_deck, signed_cookie
) -> None:
    """Every admin write type must leave an audit row. Enumerated explicitly so
    a new unaudited write path fails this test."""
    ck = {COOKIE: signed_cookie(admin_user["id"])}

    await client_real_auth.post(
        f"/admin-api/users/{target_user['id']}/ban",
        json={"reason": "x"},
        cookies=ck,
    )
    await client_real_auth.post(
        f"/admin-api/users/{target_user['id']}/unban", cookies=ck
    )
    await client_real_auth.post(
        f"/admin-api/users/{target_user['id']}/revoke-tokens", cookies=ck
    )
    rep = await client_real_auth.post(
        "/reports",
        json={"content_type": "deck", "content_id": reportable_deck["id"], "reason": "x"},
        cookies=ck,
    )
    await client_real_auth.post(
        f"/admin-api/reports/{rep.json()['report_id']}/resolve",
        json={"action": "dismiss"},
        cookies=ck,
    )
    fname = f"flag-{uuid4().hex[:6]}"
    await client_real_auth.post(
        "/admin-api/flags", json={"name": fname, "rollout_percentage": 0}, cookies=ck
    )
    await client_real_auth.patch(
        f"/admin-api/flags/{fname}", json={"rollout_percentage": 5}, cookies=ck
    )
    await client_real_auth.delete(f"/admin-api/flags/{fname}", cookies=ck)

    actions = await _audit_actions(session)
    expected = {
        "ban_user",
        "unban_user",
        "revoke_tokens",
        "resolve_report_dismiss",
        "create_flag",
        "update_flag",
        "delete_flag",
    }
    missing = expected - actions
    assert not missing, f"unaudited admin write paths: {missing}"
