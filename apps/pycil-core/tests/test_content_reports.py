"""Content-reports moderation pipeline tests (Phase 5).

- authed user creates a report → row status=pending.
- duplicate pending report for same content → 409.
- reporter reporting own content → 400.
- non-admin → /admin-api/reports* 403.
- admin list filters by status.
- admin resolve dismiss → status dismissed, audit row, content untouched.
- admin resolve delete_content (comment) → comment soft-deleted, status actioned.
- admin resolve delete_content (deck) → node deleted_at set.
"""
from __future__ import annotations

from uuid import uuid4

import pytest_asyncio
from sqlalchemy import text

from pycil_core.config import get_settings


@pytest_asyncio.fixture
async def public_deck(session, second_user) -> dict:
    """A PUBLIC deck owned by `second_user` (so the default test user can report it)."""
    row = (
        await session.execute(
            text(
                "INSERT INTO nodes (author_id, type, name, visibility) "
                "VALUES (:a, 'DECK'::node_type, 'Reported Deck', 'PUBLIC'::visibility) "
                "RETURNING id"
            ),
            {"a": second_user["id"]},
        )
    ).one()
    await session.commit()
    return {"id": str(row.id), "owner": second_user["id"]}


@pytest_asyncio.fixture
async def comment(session, second_user) -> dict:
    """A definition comment authored by `second_user`."""
    term = (
        await session.execute(
            text(
                "INSERT INTO terms (value, type) "
                "VALUES (:v, 'SINGLE_WORD'::term_type) RETURNING id"
            ),
            {"v": f"rep-{uuid4().hex[:6]}"},
        )
    ).one()
    definition = (
        await session.execute(
            text(
                "INSERT INTO definitions (term_id, synonyms, antonyms, notes) "
                "VALUES (:t, '{}', '{}', '{}') RETURNING id"
            ),
            {"t": term.id},
        )
    ).one()
    c = (
        await session.execute(
            text(
                "INSERT INTO definition_comments (definition_id, author_id, body) "
                "VALUES (:d, :a, 'offensive comment') RETURNING id"
            ),
            {"d": definition.id, "a": second_user["id"]},
        )
    ).one()
    await session.commit()
    return {"id": int(c.id), "owner": second_user["id"]}


async def _count_reports(session, status: str) -> int:
    return (
        await session.execute(
            text("SELECT COUNT(*) AS c FROM content_reports WHERE status = :s"),
            {"s": status},
        )
    ).one().c


# ── user create ─────────────────────────────────────────────────────────────


async def test_user_creates_report(client, public_deck) -> None:
    resp = await client.post(
        "/reports",
        json={"content_type": "deck", "content_id": public_deck["id"], "reason": "spam"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


async def test_duplicate_pending_report_409(client, public_deck) -> None:
    body = {"content_type": "deck", "content_id": public_deck["id"], "reason": "spam"}
    assert (await client.post("/reports", json=body)).status_code == 200
    assert (await client.post("/reports", json=body)).status_code == 409


async def test_self_report_forbidden(client, session, test_user) -> None:
    # A deck owned by the reporter themselves.
    row = (
        await session.execute(
            text(
                "INSERT INTO nodes (author_id, type, name, visibility) "
                "VALUES (:a, 'DECK'::node_type, 'Mine', 'PUBLIC'::visibility) RETURNING id"
            ),
            {"a": test_user["id"]},
        )
    ).one()
    await session.commit()
    resp = await client.post(
        "/reports",
        json={"content_type": "deck", "content_id": str(row.id), "reason": "x"},
    )
    assert resp.status_code == 400


# ── admin authz + list ───────────────────────────────────────────────────────


async def test_non_admin_forbidden(client) -> None:
    assert (await client.get("/admin-api/reports")).status_code == 403
    assert (
        await client.post("/admin-api/reports/1/resolve", json={"action": "dismiss"})
    ).status_code == 403


async def test_admin_lists_pending(
    client_real_auth, session, public_deck, test_user, admin_user, signed_cookie
) -> None:
    cookie_name = get_settings().session_cookie_name
    await client_real_auth.post(
        "/reports",
        json={"content_type": "deck", "content_id": public_deck["id"], "reason": "spam"},
        cookies={cookie_name: signed_cookie(test_user["id"])},
    )
    resp = await client_real_auth.get(
        "/admin-api/reports",
        params={"status": "pending"},
        cookies={cookie_name: signed_cookie(admin_user["id"])},
    )
    assert resp.status_code == 200
    reports = resp.json()["reports"]
    assert len(reports) == 1
    assert reports[0]["content_type"] == "deck"
    assert reports[0]["node_id"] == public_deck["id"]


# ── admin resolve ─────────────────────────────────────────────────────────────


async def _make_report_realauth(
    client_real_auth, cookie_name, user_cookie, *, content_type: str, content_id: str
) -> int:
    resp = await client_real_auth.post(
        "/reports",
        json={"content_type": content_type, "content_id": content_id, "reason": "bad"},
        cookies={cookie_name: user_cookie},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["report_id"]


async def test_resolve_dismiss_leaves_content(
    client_real_auth, session, public_deck, test_user, admin_user, signed_cookie
) -> None:
    cookie_name = get_settings().session_cookie_name
    rid = await _make_report_realauth(
        client_real_auth,
        cookie_name,
        signed_cookie(test_user["id"]),
        content_type="deck",
        content_id=public_deck["id"],
    )
    resp = await client_real_auth.post(
        f"/admin-api/reports/{rid}/resolve",
        json={"action": "dismiss"},
        cookies={cookie_name: signed_cookie(admin_user["id"])},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "dismissed"

    # Content untouched.
    node = (
        await session.execute(
            text("SELECT deleted_at FROM nodes WHERE id = CAST(:i AS uuid)"),
            {"i": public_deck["id"]},
        )
    ).one()
    assert node.deleted_at is None
    # Audit row written.
    audit = (
        await session.execute(
            text(
                "SELECT COUNT(*) AS c FROM admin_actions "
                "WHERE action = 'resolve_report_dismiss'"
            )
        )
    ).one()
    assert audit.c == 1


async def test_resolve_delete_comment_soft_deletes(
    client_real_auth, session, comment, test_user, admin_user, signed_cookie
) -> None:
    cookie_name = get_settings().session_cookie_name
    rid = await _make_report_realauth(
        client_real_auth,
        cookie_name,
        signed_cookie(test_user["id"]),
        content_type="comment",
        content_id=str(comment["id"]),
    )
    resp = await client_real_auth.post(
        f"/admin-api/reports/{rid}/resolve",
        json={"action": "delete_content"},
        cookies={cookie_name: signed_cookie(admin_user["id"])},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "actioned"

    row = (
        await session.execute(
            text("SELECT deleted_at FROM definition_comments WHERE id = :i"),
            {"i": comment["id"]},
        )
    ).one()
    assert row.deleted_at is not None


async def test_resolve_delete_deck_soft_deletes(
    client_real_auth, session, public_deck, test_user, admin_user, signed_cookie
) -> None:
    cookie_name = get_settings().session_cookie_name
    rid = await _make_report_realauth(
        client_real_auth,
        cookie_name,
        signed_cookie(test_user["id"]),
        content_type="deck",
        content_id=public_deck["id"],
    )
    resp = await client_real_auth.post(
        f"/admin-api/reports/{rid}/resolve",
        json={"action": "delete_content"},
        cookies={cookie_name: signed_cookie(admin_user["id"])},
    )
    assert resp.status_code == 200

    node = (
        await session.execute(
            text("SELECT deleted_at FROM nodes WHERE id = CAST(:i AS uuid)"),
            {"i": public_deck["id"]},
        )
    ).one()
    assert node.deleted_at is not None


async def test_resolve_unknown_report_404(admin_client) -> None:
    resp = await admin_client.post(
        "/admin-api/reports/999999/resolve", json={"action": "dismiss"}
    )
    assert resp.status_code == 404
