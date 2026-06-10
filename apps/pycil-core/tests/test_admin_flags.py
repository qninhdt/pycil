"""Admin feature-flag CRUD tests (Phase 6).

- non-admin → all /admin-api/flags* 403.
- create flag → row persisted; is_enabled reflects rollout (cache invalidated).
- update rollout 0→100 → is_enabled flips for a bucketed user.
- rollout out of [0,100] → 422.
- delete → flag gone; is_enabled returns False.
- each write → admin_actions row.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text

from pycil_core.services import feature_flag_service


@pytest.fixture(autouse=True)
def _clear_flag_cache():
    """The in-process flag cache is module-global; reset around each test."""
    feature_flag_service.invalidate_cache()
    yield
    feature_flag_service.invalidate_cache()


async def _count_audit(session, action: str) -> int:
    return (
        await session.execute(
            text("SELECT COUNT(*) AS c FROM admin_actions WHERE action = :a"),
            {"a": action},
        )
    ).one().c


# ── authz ───────────────────────────────────────────────────────────────────


async def test_non_admin_forbidden(client) -> None:
    assert (await client.get("/admin-api/flags")).status_code == 403
    assert (
        await client.post("/admin-api/flags", json={"name": "x"})
    ).status_code == 403
    assert (
        await client.patch("/admin-api/flags/x", json={"rollout_percentage": 5})
    ).status_code == 403
    assert (await client.delete("/admin-api/flags/x")).status_code == 403


# ── create ────────────────────────────────────────────────────────────────


async def test_create_flag_persists_and_audits(admin_client, session) -> None:
    name = f"flag-{uuid4().hex[:6]}"
    resp = await admin_client.post(
        "/admin-api/flags",
        json={"name": name, "rollout_percentage": 100},
    )
    assert resp.status_code == 200

    row = (
        await session.execute(
            text("SELECT rollout_percentage FROM feature_flags WHERE name = :n"),
            {"n": name},
        )
    ).one()
    assert row.rollout_percentage == 100
    assert await _count_audit(session, "create_flag") == 1


async def test_create_then_is_enabled_reflects_rollout(admin_client, session) -> None:
    name = f"flag-{uuid4().hex[:6]}"
    await admin_client.post(
        "/admin-api/flags", json={"name": name, "rollout_percentage": 100}
    )
    # Cache was invalidated on create → fresh eval sees rollout=100.
    assert await feature_flag_service.is_enabled(session, name, uuid4()) is True


async def test_create_duplicate_409(admin_client) -> None:
    name = f"flag-{uuid4().hex[:6]}"
    assert (
        await admin_client.post(
            "/admin-api/flags", json={"name": name, "rollout_percentage": 0}
        )
    ).status_code == 200
    assert (
        await admin_client.post(
            "/admin-api/flags", json={"name": name, "rollout_percentage": 0}
        )
    ).status_code == 409


async def test_create_rollout_out_of_range_422(admin_client) -> None:
    resp = await admin_client.post(
        "/admin-api/flags",
        json={"name": f"flag-{uuid4().hex[:6]}", "rollout_percentage": 150},
    )
    assert resp.status_code == 422


# ── update ────────────────────────────────────────────────────────────────


async def test_update_rollout_flips_eval(admin_client, session) -> None:
    name = f"flag-{uuid4().hex[:6]}"
    uid = uuid4()
    await admin_client.post(
        "/admin-api/flags", json={"name": name, "rollout_percentage": 0}
    )
    assert await feature_flag_service.is_enabled(session, name, uid) is False

    resp = await admin_client.patch(
        f"/admin-api/flags/{name}", json={"rollout_percentage": 100}
    )
    assert resp.status_code == 200
    # Cache invalidated on update → eval flips to enabled.
    assert await feature_flag_service.is_enabled(session, name, uid) is True
    assert await _count_audit(session, "update_flag") == 1


async def test_update_unknown_flag_404(admin_client) -> None:
    resp = await admin_client.patch(
        f"/admin-api/flags/missing-{uuid4().hex[:6]}",
        json={"rollout_percentage": 50},
    )
    assert resp.status_code == 404


# ── delete ────────────────────────────────────────────────────────────────


async def test_delete_flag_removes_and_disables(admin_client, session) -> None:
    name = f"flag-{uuid4().hex[:6]}"
    await admin_client.post(
        "/admin-api/flags", json={"name": name, "rollout_percentage": 100}
    )
    resp = await admin_client.delete(f"/admin-api/flags/{name}")
    assert resp.status_code == 200

    gone = (
        await session.execute(
            text("SELECT COUNT(*) AS c FROM feature_flags WHERE name = :n"),
            {"n": name},
        )
    ).one()
    assert gone.c == 0
    # Absent flag → disabled (cache invalidated on delete).
    assert await feature_flag_service.is_enabled(session, name, uuid4()) is False
    assert await _count_audit(session, "delete_flag") == 1


async def test_delete_unknown_flag_404(admin_client) -> None:
    resp = await admin_client.delete(f"/admin-api/flags/missing-{uuid4().hex[:6]}")
    assert resp.status_code == 404


# ── list ────────────────────────────────────────────────────────────────────


async def test_list_flags(admin_client) -> None:
    name = f"flag-{uuid4().hex[:6]}"
    await admin_client.post(
        "/admin-api/flags", json={"name": name, "rollout_percentage": 25}
    )
    resp = await admin_client.get("/admin-api/flags")
    assert resp.status_code == 200
    names = {f["name"] for f in resp.json()["flags"]}
    assert name in names
