"""Owner-scoped receipts for best-effort content work running after HTTP responses."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid7

from fastapi import BackgroundTasks
from redis.asyncio import Redis
from redis.exceptions import WatchError

from pycil.jobs.contracts import TASK_KIND_QUESTION_SUPPLY, TASK_KIND_WORD

RECEIPT_TTL_SECONDS = 24 * 3600
# A running job is bounded by the runner at 10 minutes. Leave time for cleanup.
JOB_STALE_SECONDS = 11 * 60
TERMINAL_STATUSES = frozenset({"done", "failed", "expired"})
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_EXPIRED = "expired"


def receipt_key(job_id: str) -> str:
    return f"pycil:job:{job_id}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def effective_status(data: dict, *, now: datetime | None = None) -> str:
    status = data.get("status", STATUS_QUEUED)
    if status in TERMINAL_STATUSES:
        return status
    if status not in (STATUS_QUEUED, STATUS_RUNNING):
        return status
    created = data.get("createdAt")
    try:
        age = ((now or datetime.now(UTC)) - datetime.fromisoformat(created)).total_seconds()
        if age >= JOB_STALE_SECONDS:
            return STATUS_EXPIRED
    except ValueError, TypeError:
        return STATUS_EXPIRED
    return status


async def enqueue_job(
    redis: Redis,
    background_tasks: BackgroundTasks,
    job_type: str,
    payload: dict,
    owner_id: str,
    job_id: str | None = None,
) -> str:
    """Record work before responding; the callback runs only after the response."""
    if job_type not in (TASK_KIND_WORD, TASK_KIND_QUESTION_SUPPLY):
        raise ValueError(f"unknown_job_kind: {job_type}")
    resolved_id = job_id or str(uuid7())
    created = _now_iso()
    await redis.set(
        receipt_key(resolved_id),
        json.dumps(
            {
                "id": resolved_id,
                "kind": job_type,
                "owner_id": owner_id,
                "status": STATUS_QUEUED,
                "createdAt": created,
                "updatedAt": created,
                "result": None,
                "errorCode": None,
            }
        ),
        ex=RECEIPT_TTL_SECONDS,
    )
    try:
        from pycil.jobs.runner import run_job

        background_tasks.add_task(run_job, resolved_id, job_type, payload)
    except Exception:
        await redis.delete(receipt_key(resolved_id))
        raise
    return resolved_id


async def update_job_status(
    redis: Redis,
    job_id: str,
    status: str,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    """Keep terminal/expired receipts terminal, including when a task finishes late."""
    key = receipt_key(job_id)
    async with redis.pipeline() as pipe:
        while True:
            try:
                await pipe.watch(key)
                raw = await pipe.get(key)
                if not raw:
                    return
                data = json.loads(raw)
                if effective_status(data) in TERMINAL_STATUSES:
                    return
                now = _now_iso()
                data["status"] = status
                data["updatedAt"] = now
                if result is not None:
                    data["result"] = result
                if error is not None:
                    data["errorCode"] = error
                if status in TERMINAL_STATUSES:
                    data["finishedAt"] = now
                pipe.multi()
                pipe.set(key, json.dumps(data), ex=RECEIPT_TTL_SECONDS)
                await pipe.execute()
                return
            except WatchError:
                continue


async def read_receipt(redis: Redis, job_id: str) -> dict | None:
    raw = await redis.get(receipt_key(job_id))
    if not raw:
        return None
    data = json.loads(raw)
    if effective_status(data) == STATUS_EXPIRED:
        data["status"] = STATUS_EXPIRED
    return data
