"""SSE stream service for term-generation jobs.

Semantics:

- Always returns 404 for "job not found" AND "user does not own job" — no
  timing oracle that would let an attacker enumerate term ids by job id.
- Reads the `jobs` row FIRST. If already terminal (completed/failed),
  emits one final SSE frame and closes WITHOUT subscribing — avoids the
  "missed-event on reconnect" race entirely.
- Otherwise subscribes Redis `results:{term_id}` (worker publishes here
  on completion). 15s heartbeats. Hard 60s connection cap; client
  reconnects on close.
- `try/finally` always closes the pubsub.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
from shared.db import Job, UserTermJob
from sqlalchemy import and_, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from pycil_core.services.redis_pool import get_redis

_HEARTBEAT_INTERVAL = 15.0
_MAX_DURATION = 60.0


def _redis() -> Redis:
    return get_redis()


def _sse_frame(event: str, data: Any) -> bytes:
    payload = data if isinstance(data, str) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n".encode()


async def _load_owned_job(
    session: AsyncSession, *, user_id: UUID, job_id: UUID
) -> dict:
    """Return job row dict if user owns it; raise 404 otherwise (no oracle)."""
    stmt = (
        select(
            Job.id,
            Job.type,
            Job.status,
            Job.result,
            Job.error,
            Job.payload,
            UserTermJob.last_event,
        )
        .select_from(Job)
        .outerjoin(
            UserTermJob,
            and_(
                UserTermJob.job_id == Job.id,
                UserTermJob.user_id == user_id,
            ),
        )
        .where(
            Job.id == job_id,
            or_(
                UserTermJob.user_id.is_not(None),
                Job.created_by_user_id == user_id,
            ),
        )
        .limit(1)
    )
    row = (await session.exec(stmt)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job_not_found")
    payload = row.payload
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = {}
    result = row.result
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (TypeError, ValueError):
            pass
    return {
        "id": str(row.id),
        "type": row.type,
        "status": row.status,
        "result": result,
        "error": row.error,
        "term_id": (payload or {}).get("term_id"),
        "last_event": row.last_event,
    }


async def stream_job(
    session: AsyncSession, *, user_id: UUID, job_id: UUID
) -> AsyncGenerator[bytes, None]:
    """Yield SSE frames for a job. See module docstring for invariants."""
    job = await _load_owned_job(session, user_id=user_id, job_id=job_id)

    if job["status"] in ("completed", "failed"):
        # Prefer last_event JSONB (full terminal payload) when present;
        # fall back to the loaded job dict.
        yield _sse_frame("status", job["last_event"] or job)
        return

    # Channel selection: term-generation jobs publish on results:{term_id};
    # grade_answer jobs (no term_id) publish on results:job_{job_id}. Other
    # non-term jobs (translate/tts) have no live stream — emit one frame + close
    # exactly as before (do NOT subscribe a channel nobody publishes to).
    term_id = job.get("term_id")
    if term_id is not None:
        channel = f"results:{term_id}"
    elif job.get("type") == "grade_answer":
        channel = f"results:job_{job['id']}"
    else:
        yield _sse_frame("status", job)
        return

    yield _sse_frame("status", {"id": job["id"], "status": job["status"]})

    redis = _redis()
    pubsub = redis.pubsub()
    started = asyncio.get_event_loop().time()
    try:
        await pubsub.subscribe(channel)
        last_beat = started
        while True:
            now = asyncio.get_event_loop().time()
            if now - started >= _MAX_DURATION:
                yield _sse_frame("timeout", {"id": job["id"]})
                return

            timeout = min(_HEARTBEAT_INTERVAL, _MAX_DURATION - (now - started))
            msg = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=timeout
            )
            if msg is None:
                if asyncio.get_event_loop().time() - last_beat >= _HEARTBEAT_INTERVAL:
                    yield b": heartbeat\n\n"
                    last_beat = asyncio.get_event_loop().time()
                continue

            data = msg.get("data")
            if isinstance(data, bytes):
                data = data.decode()
            try:
                payload = json.loads(data) if isinstance(data, str) else data
            except (TypeError, ValueError):
                payload = {"raw": data}
            yield _sse_frame("status", payload)
            if isinstance(payload, dict) and payload.get("status") in (
                "completed",
                "failed",
            ):
                return
    finally:
        try:
            await pubsub.unsubscribe(channel)
        finally:
            try:
                await pubsub.aclose()
            finally:
                await asyncio.shield(redis.aclose())
