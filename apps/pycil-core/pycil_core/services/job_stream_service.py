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
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil_core.config import get_settings


_HEARTBEAT_INTERVAL = 15.0
_MAX_DURATION = 60.0


def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def _sse_frame(event: str, data: Any) -> bytes:
    payload = data if isinstance(data, str) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n".encode()


async def _load_owned_job(
    session: AsyncSession, *, user_id: UUID, job_id: UUID
) -> dict:
    """Return job row dict if user owns it; raise 404 otherwise (no oracle)."""
    row = (
        await session.execute(
            text(
                """
                SELECT j.id, j.type, j.status, j.result, j.error, j.payload
                FROM jobs j
                JOIN user_term_jobs utj ON utj.job_id = j.id
                WHERE j.id = :jid AND utj.user_id = :uid
                LIMIT 1
                """
            ),
            {"jid": job_id, "uid": user_id},
        )
    ).first()
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
    }


async def stream_job(
    session: AsyncSession, *, user_id: UUID, job_id: UUID
) -> AsyncGenerator[bytes, None]:
    """Yield SSE frames for a job. See module docstring for invariants."""
    job = await _load_owned_job(session, user_id=user_id, job_id=job_id)

    if job["status"] in ("completed", "failed"):
        yield _sse_frame("status", job)
        return

    term_id = job.get("term_id")
    if term_id is None:
        yield _sse_frame("status", job)
        return

    yield _sse_frame("status", {"id": job["id"], "status": job["status"]})

    redis = _redis()
    pubsub = redis.pubsub()
    channel = f"results:{term_id}"
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
