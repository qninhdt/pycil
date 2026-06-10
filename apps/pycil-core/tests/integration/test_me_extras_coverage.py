"""Coverage tests for pycil_core.api.routes.me_extras.

Exercises the social (follow/like), ToS ack, term-notes, daily-goal,
CEFR threshold, activity-feed, feature-flag, and admin audit-viewer
routes wired in this module.
"""
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text

from pycil_core.config import get_settings

COOKIE = get_settings().session_cookie_name


# ── follow ──────────────────────────────────────────────────────────────────


async def test_follow_unknown_username_404(client) -> None:
    resp = await client.post("/me/follow/nobody_here")
    assert resp.status_code == 404


async def test_follow_toggle_on_then_off(client, session, second_user) -> None:
    # Give the followee a username so the lookup resolves.
    uname = f"u{uuid4().hex[:8]}"
    await session.execute(
        text("UPDATE users SET username = :u WHERE id = :id"),
        {"u": uname, "id": second_user["id"]},
    )
    await session.commit()

    on = await client.post(f"/me/follow/{uname}")
    assert on.status_code == 200
    assert on.json()["following"] is True

    off = await client.post(f"/me/follow/{uname}")
    assert off.status_code == 200
    assert off.json()["following"] is False


# ── deck like ─────────────────────────────────────────────────────────────


async def test_like_toggle_on_then_off(client, session, test_user) -> None:
    deck = (
        await session.execute(
            text(
                "INSERT INTO nodes (author_id, type, name, visibility) "
                "VALUES (:a, 'DECK'::node_type, 'Likeable', 'PUBLIC'::visibility) "
                "RETURNING id"
            ),
            {"a": test_user["id"]},
        )
    ).one()
    await session.commit()

    on = await client.post(f"/decks/{deck.id}/like")
    assert on.status_code == 200
    assert on.json()["liked"] is True

    off = await client.post(f"/decks/{deck.id}/like")
    assert off.status_code == 200
    assert off.json()["liked"] is False


# ── push subscribe / unsubscribe ──────────────────────────────────────────


async def test_push_subscribe_then_unsubscribe(client) -> None:
    payload = {
        "endpoint": "https://push.example/abc",
        "p256dh": "key1",
        "auth": "auth1",
    }
    sub = await client.post("/push/subscribe", json=payload)
    assert sub.status_code == 200
    assert "subscription_id" in sub.json()

    unsub = await client.request("DELETE", "/push/subscribe", json=payload)
    assert unsub.status_code == 200
    assert unsub.json()["removed"] is True


# ── ToS gating ─────────────────────────────────────────────────────────────


async def test_tos_needs_ack_none_pending(client) -> None:
    resp = await client.get("/tos/needs-ack")
    assert resp.status_code == 200
    assert resp.json()["needs_ack"] is False


async def test_tos_needs_ack_and_ack_flow(client, session) -> None:
    version = f"v{uuid4().hex[:6]}"
    await session.execute(
        text(
            "INSERT INTO tos_versions (version, summary, body_md, effective_at) "
            "VALUES (:v, 'Summary', 'Body', NOW())"
        ),
        {"v": version},
    )
    await session.commit()

    pending = await client.get("/tos/needs-ack")
    assert pending.status_code == 200
    assert pending.json()["needs_ack"] is True
    assert pending.json()["version"] == version

    acked = await client.post(f"/tos/{version}/ack")
    assert acked.status_code == 200
    assert acked.json()["ack"] is True

    after = await client.get("/tos/needs-ack")
    assert after.json()["needs_ack"] is False


# ── term notes ──────────────────────────────────────────────────────────────


async def test_term_note_get_empty(client) -> None:
    resp = await client.get("/me/notes/12345")
    assert resp.status_code == 200
    assert resp.json()["body"] is None


async def test_term_note_put_get_delete(client) -> None:
    term_id = 4242
    put = await client.put(f"/me/notes/{term_id}", json={"body": "my note"})
    assert put.status_code == 200
    assert put.json()["saved"] is True

    got = await client.get(f"/me/notes/{term_id}")
    assert got.json()["body"] == "my note"

    deleted = await client.delete(f"/me/notes/{term_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    assert (await client.get(f"/me/notes/{term_id}")).json()["body"] is None


# ── daily goal ────────────────────────────────────────────────────────────


async def test_get_my_goal_defaults(client) -> None:
    resp = await client.get("/me/goal")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("daily_goal", "answered_today", "correct_today", "streak_days"):
        assert key in body


async def test_update_my_goal(client) -> None:
    resp = await client.patch(
        "/me/goal", json={"daily_goal": 30, "reminder_hour": 9}
    )
    assert resp.status_code == 200
    assert resp.json()["daily_goal"] == 30


# ── CEFR thresholds ──────────────────────────────────────────────────────


async def test_get_cefr_thresholds_defaults(client) -> None:
    resp = await client.get("/me/cefr-thresholds")
    assert resp.status_code == 200
    body = resp.json()
    assert body["A1"] == 5


async def test_put_cefr_thresholds_override(client) -> None:
    resp = await client.put(
        "/me/cefr-thresholds", json={"thresholds": {"A1": 3, "C2": 12}}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["A1"] == 3
    assert body["C2"] == 12


# ── activity feed ───────────────────────────────────────────────────────────


async def test_my_feed_empty(client) -> None:
    resp = await client.get("/me/feed")
    assert resp.status_code == 200
    assert resp.json()["events"] == []


# ── feature flag eval ─────────────────────────────────────────────────────


async def test_get_flag_unknown_disabled(client) -> None:
    resp = await client.get(f"/flags/unknown-{uuid4().hex[:6]}")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


async def test_get_flag_full_rollout_enabled(client, session) -> None:
    from pycil_core.services.feature_flag_service import invalidate_cache

    name = f"flag-{uuid4().hex[:6]}"
    await session.execute(
        text(
            "INSERT INTO feature_flags (name, rollout_percentage) "
            "VALUES (:n, 100)"
        ),
        {"n": name},
    )
    await session.commit()
    invalidate_cache()

    resp = await client.get(f"/flags/{name}")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True
    invalidate_cache()


# ── admin audit viewer (AdminDep-gated) ────────────────────────────────────


async def test_audit_viewer_non_admin_forbidden(client) -> None:
    assert (await client.get("/admin-api/audit")).status_code == 403


async def test_audit_viewer_lists_with_filters(admin_client, session, admin_user) -> None:
    target = uuid4()
    for action in ("ban_user", "unban_user"):
        await session.execute(
            text(
                "INSERT INTO admin_actions "
                "(actor_user_id, target_user_id, action, metadata) "
                "VALUES (:a, :t, :act, '{}'::jsonb)"
            ),
            {"a": admin_user["id"], "t": str(target), "act": action},
        )
    await session.commit()

    resp = await admin_client.get("/admin-api/audit")
    assert resp.status_code == 200
    assert len(resp.json()["actions"]) >= 2

    filtered = await admin_client.get(
        "/admin-api/audit", params={"action": "ban_user", "target": str(target)}
    )
    assert filtered.status_code == 200
    acts = filtered.json()["actions"]
    assert all(a["action"] == "ban_user" for a in acts)


async def test_audit_viewer_cursor_pagination(admin_client, session, admin_user) -> None:
    for _ in range(3):
        await session.execute(
            text(
                "INSERT INTO admin_actions (actor_user_id, action, metadata) "
                "VALUES (:a, 'noop', '{}'::jsonb)"
            ),
            {"a": admin_user["id"]},
        )
    await session.commit()

    page1 = await admin_client.get("/admin-api/audit", params={"limit": 2})
    assert page1.status_code == 200
    body1 = page1.json()
    assert len(body1["actions"]) == 2
    assert body1["next_cursor"] is not None

    page2 = await admin_client.get(
        "/admin-api/audit", params={"limit": 2, "cursor": body1["next_cursor"]}
    )
    assert page2.status_code == 200
    ids1 = {a["id"] for a in body1["actions"]}
    ids2 = {a["id"] for a in page2.json()["actions"]}
    assert ids1.isdisjoint(ids2)
