"""Admin system-health snapshot (Phase 7), gated by `AdminDep`.

Four bounded, never-throw checks — a down dependency reports `fail`, never a
500 (red-team F7: inline, no health_service module until logic grows):
- DB: `SELECT 1`
- Redis: `PING`
- queue_depth: `ZCARD arq:queue` (arq stores its queue as a sorted set — F11
  mandates ZCARD, NOT LLEN which would WRONGTYPE).
- worker_heartbeat_age_s: age of the `worker:heartbeat` Redis key the worker
  refreshes via cron; null if absent.

Mounts under `/admin-api/health`.
"""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter
from sqlalchemy import text

from pycil_core.api.deps import AdminDep, RedisDep, SessionDep

router = APIRouter(prefix="/admin-api/health", tags=["admin-health"])

_PING_TIMEOUT_S = 2.0
_ARQ_QUEUE_KEY = "arq:queue"
_WORKER_HEARTBEAT_KEY = "worker:heartbeat"


@router.get("")
async def health(admin: AdminDep, session: SessionDep, redis: RedisDep) -> dict:
    db_status = "ok"
    try:
        await asyncio.wait_for(session.execute(text("SELECT 1")), _PING_TIMEOUT_S)
    except Exception:  # noqa: BLE001
        db_status = "fail"

    redis_status = "ok"
    queue_depth: int | None = None
    heartbeat_age: float | None = None
    try:
        await asyncio.wait_for(redis.ping(), _PING_TIMEOUT_S)
        try:
            queue_depth = int(await redis.zcard(_ARQ_QUEUE_KEY))
        except Exception:  # noqa: BLE001
            queue_depth = None
        try:
            raw = await redis.get(_WORKER_HEARTBEAT_KEY)
            if raw is not None:
                ts = float(raw if not isinstance(raw, bytes) else raw.decode())
                heartbeat_age = max(0.0, round(time.time() - ts, 1))
        except Exception:  # noqa: BLE001
            heartbeat_age = None
    except Exception:  # noqa: BLE001
        redis_status = "fail"

    return {
        "db": db_status,
        "redis": redis_status,
        "queue_depth": queue_depth,
        "worker_heartbeat_age_s": heartbeat_age,
    }
