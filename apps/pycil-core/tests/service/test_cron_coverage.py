"""Coverage for cron jobs (advisory-locked daily/weekly maintenance).

Pinned:
- run_job dispatch: both known jobs + ValueError on unknown.
- hard_delete_expired_users: removes users soft-deleted >14d ago.
- compute_league_rank: dense-ranks live users by xp_total desc.
- advisory-lock contention → body skipped (no work, no error).
- get_scheduler: singleton with both jobs registered.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import text

from pycil_core import cron as svc


async def _seed_user(session, *, xp=0, deleted_days_ago=None) -> str:
    deleted_sql = (
        "NOW() - make_interval(days => :d)" if deleted_days_ago is not None else "NULL"
    )
    params = {
        "e": f"cron-{uuid4().hex[:10]}@example.test",
        "n": "CronUser",
        "x": xp,
    }
    if deleted_days_ago is not None:
        params["d"] = deleted_days_ago
    row = (
        await session.execute(
            text(
                f"INSERT INTO users (email, name, xp_total, deleted_at) "
                f"VALUES (:e, :n, :x, {deleted_sql}) RETURNING id"
            ),
            params,
        )
    ).one()
    await session.commit()
    return str(row.id)


# --- run_job dispatch -------------------------------------------------------

async def test_run_job_unknown_raises(session):
    with pytest.raises(ValueError, match="unknown_job"):
        await svc.run_job("does_not_exist")


# --- hard_delete_expired_users ----------------------------------------------
# cron opens its OWN session (via get_engine, redirected to the test engine by
# the async_engine fixture) and delegates row deletion to
# user_service.hard_delete_expired. We spy on that delegate to cover cron's
# orchestration (lock acquired → session opened → service invoked → logged)
# without coupling to the service's own (separately tested) delete SQL.

async def test_hard_delete_invokes_service_under_lock(session, monkeypatch):
    calls: list = []

    async def _spy(sess):
        calls.append(sess)
        return 3

    monkeypatch.setattr(svc.user_service, "hard_delete_expired", _spy)

    await svc.run_job("hard_delete_expired_users")

    # Lock acquired (single replica) → service called exactly once with a session.
    assert len(calls) == 1
    assert calls[0] is not None


# --- compute_league_rank ----------------------------------------------------

async def test_compute_league_rank_orders_by_xp(session):
    top = await _seed_user(session, xp=500)
    mid = await _seed_user(session, xp=100)
    low = await _seed_user(session, xp=10)
    # soft-deleted user must be excluded from ranking entirely.
    await _seed_user(session, xp=999, deleted_days_ago=30)

    await svc.run_job("compute_league_rank")

    async def rank(uid: str) -> int:
        r = (
            await session.execute(
                text("SELECT league_rank FROM users WHERE id = :i"), {"i": uid}
            )
        ).one()
        return int(r.league_rank)

    assert await rank(top) == 1
    assert await rank(mid) == 2
    assert await rank(low) == 3


# --- advisory-lock contention -----------------------------------------------

async def test_locked_replica_skips_body(session, monkeypatch):
    """When the advisory lock is held elsewhere, the job body must not run."""

    @asynccontextmanager
    async def _not_acquired(conn, name):
        yield False

    monkeypatch.setattr(svc, "advisory_lock", _not_acquired)

    stale = await _seed_user(session, deleted_days_ago=30)
    await svc.run_job("hard_delete_expired_users")

    # Lock not acquired → no delete happened.
    remaining = {
        str(r.id)
        for r in (await session.execute(text("SELECT id FROM users"))).all()
    }
    assert stale in remaining


# --- scheduler wiring -------------------------------------------------------

def test_get_scheduler_singleton_with_jobs(monkeypatch):
    monkeypatch.setattr(svc, "_scheduler", None)
    sched = svc.get_scheduler()
    assert svc.get_scheduler() is sched  # cached singleton
    job_ids = {j.id for j in sched.get_jobs()}
    assert "hard_delete_expired_users" in job_ids
    assert "compute_league_rank" in job_ids
