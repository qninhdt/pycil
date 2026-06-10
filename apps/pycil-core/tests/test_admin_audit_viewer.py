"""Admin audit-log viewer tests (Phase 7).

The viewer reuses the previously-dead `/admin/audit` handler, re-gated to
AdminDep and re-mounted at `/admin-api/audit` with filters + pagination (F5).

- non-admin → 403.
- admin → returns seeded admin_actions.
- action / target filters narrow results.
- pagination cursor works.
"""
from __future__ import annotations

from uuid import uuid4

import pytest_asyncio
from sqlalchemy import text


@pytest_asyncio.fixture
async def seeded_actions(session, admin_user) -> dict:
    """Insert a handful of admin_actions for the admin actor."""
    actor = admin_user["id"]
    targets = [uuid4() for _ in range(3)]
    # 3 ban_user actions + 2 unban_user actions.
    for t in targets:
        await session.execute(
            text(
                "INSERT INTO admin_actions (actor_user_id, target_user_id, action, metadata) "
                "VALUES (:a, :t, 'ban_user', '{}'::jsonb)"
            ),
            {"a": actor, "t": t},
        )
    for t in targets[:2]:
        await session.execute(
            text(
                "INSERT INTO admin_actions (actor_user_id, target_user_id, action, metadata) "
                "VALUES (:a, :t, 'unban_user', '{}'::jsonb)"
            ),
            {"a": actor, "t": t},
        )
    await session.commit()
    return {"actor": str(actor), "targets": [str(t) for t in targets]}


async def test_non_admin_forbidden(client) -> None:
    assert (await client.get("/admin-api/audit")).status_code == 403


async def test_admin_lists_actions(admin_client, seeded_actions) -> None:
    resp = await admin_client.get("/admin-api/audit")
    assert resp.status_code == 200
    actions = resp.json()["actions"]
    assert len(actions) == 5


async def test_filter_by_action(admin_client, seeded_actions) -> None:
    resp = await admin_client.get("/admin-api/audit", params={"action": "ban_user"})
    assert resp.status_code == 200
    actions = resp.json()["actions"]
    assert len(actions) == 3
    assert all(a["action"] == "ban_user" for a in actions)


async def test_filter_by_target(admin_client, seeded_actions) -> None:
    target = seeded_actions["targets"][0]
    resp = await admin_client.get("/admin-api/audit", params={"target": target})
    assert resp.status_code == 200
    actions = resp.json()["actions"]
    # target[0] has both a ban and an unban.
    assert len(actions) == 2
    assert all(a["target_user_id"] == target for a in actions)


async def test_pagination_cursor(admin_client, seeded_actions) -> None:
    first = await admin_client.get("/admin-api/audit", params={"limit": 2})
    assert first.status_code == 200
    body = first.json()
    assert len(body["actions"]) == 2
    assert body["next_cursor"] is not None

    second = await admin_client.get(
        "/admin-api/audit", params={"limit": 2, "cursor": body["next_cursor"]}
    )
    assert second.status_code == 200
    body2 = second.json()
    # Cursor pages strictly older ids → no overlap.
    first_ids = {a["id"] for a in body["actions"]}
    second_ids = {a["id"] for a in body2["actions"]}
    assert first_ids.isdisjoint(second_ids)
