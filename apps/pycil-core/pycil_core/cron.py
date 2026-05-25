"""apscheduler cron jobs for pycil-core.

All jobs MUST acquire `pg_advisory_xact_lock(hash('cron-name'))` before
running their body — guards against double-fire across pycil-core
replicas. Use `services.cache.advisory_lock(conn, name)` as contextmanager.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from pycil_core.db import get_engine
from pycil_core.services import user_service
from pycil_core.services.cache import advisory_lock


logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


async def _hard_delete_expired_users() -> None:
    """Daily 03:00 UTC: drop users soft-deleted >14d ago."""
    engine = get_engine()
    async with engine.begin() as conn:
        async with advisory_lock(conn, "hard_delete_expired_users") as acquired:
            if not acquired:
                logger.info("hard_delete_expired_users: lock held by another replica")
                return
            from sqlalchemy.ext.asyncio import AsyncSession

            async with AsyncSession(engine, expire_on_commit=False) as session:
                count = await user_service.hard_delete_expired(session)
                logger.info("hard_delete_expired_users: removed=%d", count)


async def _compute_league_rank() -> None:
    """Weekly Mon 00:00 UTC: recompute users.league_rank based on xp_total."""
    from sqlalchemy import text

    engine = get_engine()
    async with engine.begin() as conn:
        async with advisory_lock(conn, "compute_league_rank") as acquired:
            if not acquired:
                logger.info("compute_league_rank: lock held by another replica")
                return
            await conn.execute(
                text(
                    """
                    WITH ranked AS (
                        SELECT id, RANK() OVER (ORDER BY xp_total DESC) AS r
                          FROM users
                         WHERE deleted_at IS NULL
                    )
                    UPDATE users u
                       SET league_rank = ranked.r
                      FROM ranked
                     WHERE u.id = ranked.id
                    """
                )
            )
            logger.info("compute_league_rank: ok")


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    sched = AsyncIOScheduler(timezone="UTC")
    sched.add_job(
        _hard_delete_expired_users,
        CronTrigger(hour=3, minute=0),
        id="hard_delete_expired_users",
        replace_existing=True,
    )
    sched.add_job(
        _compute_league_rank,
        CronTrigger(day_of_week="mon", hour=0, minute=0),
        id="compute_league_rank",
        replace_existing=True,
    )
    _scheduler = sched
    return sched


async def run_job(name: str) -> None:
    """Manual run for ops/testing: `python -m pycil_core.cron run <name>`."""
    if name == "hard_delete_expired_users":
        await _hard_delete_expired_users()
    elif name == "compute_league_rank":
        await _compute_league_rank()
    else:
        raise ValueError(f"unknown_job: {name}")


if __name__ == "__main__":
    import asyncio
    import sys

    if len(sys.argv) >= 3 and sys.argv[1] == "run":
        asyncio.run(run_job(sys.argv[2]))
    else:
        print("Usage: python -m pycil_core.cron run <job_name>", file=sys.stderr)
        sys.exit(2)
