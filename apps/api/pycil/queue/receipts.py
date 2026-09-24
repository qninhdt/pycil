"""Content-job publication and the owner-scoped job receipt.

The API publishes through Taskiq's Redis Streams broker rather than writing to a
Redis list itself. Streams give the worker consumer-group delivery with explicit
ACK and reclaim, which is what makes a crashed worker's job recoverable without a
starting worker stealing work another live worker is running.

Delivery is at-least-once. The effect is made idempotent at the content boundary
(Lexi's uniqueness rule), so a redelivery after a committed write returns the
existing row instead of paying for a second generation. Nothing here promises
exactly-once.

The receipt is a small Redis record keyed by job id and carrying the owner. It is
status and result-reference only: never a credential, a provider payload or a
full document. A missing receipt means the caller should retry, not that the work
succeeded.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from redis.asyncio import Redis
from taskiq import BrokerMessage, TaskiqMessage

from pycil.queue.broker import get_broker
from pycil.queue.contracts import (
    JOB_NAME_FOR_KIND,
    PAYLOAD_VERSION,
    TASK_KIND_QUESTION_SUPPLY,
    TASK_KIND_WORD,
)

#: Receipt lifetime. Long enough that a study client polling a slow provider
#: still sees its own job, short enough that abandoned work does not accumulate.
RECEIPT_TTL_SECONDS = 24 * 3600

#: Terminal states. A receipt in one of these is final; anything else means the
#: client should keep waiting or retry.
TERMINAL_STATUSES = frozenset({"done", "failed", "expired"})

#: The statuses a caller may observe, mirroring the phase's contract.
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_EXPIRED = "expired"


def receipt_key(job_id: str) -> str:
    return f"pycil:job:{job_id}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _publish_message(job_id: str, kind: str, payload: dict) -> BrokerMessage:
    """The exact bytes a worker will decode, built through Taskiq's own formatter.

    Building the message here rather than hand-rolling JSON is what keeps the
    producer and the receiver agreeing on the envelope: the worker decodes with
    the same formatter this encodes with.
    """
    task_name = JOB_NAME_FOR_KIND.get(kind)
    if task_name is None:
        raise ValueError(f"unknown_job_kind: {kind}")
    message = TaskiqMessage(
        task_id=job_id,
        task_name=task_name,
        labels={},
        args=[],
        kwargs={
            "job_id": job_id,
            "payload": payload,
            "payload_version": PAYLOAD_VERSION,
        },
    )
    return get_broker().formatter.dumps(message)


async def enqueue_job(
    redis: Redis,
    job_type: str,
    payload: dict,
    owner_id: str,
    job_id: str | None = None,
) -> str:
    """Publish one content job and return its receipt id.

    The receipt is written before publication. If publication then fails the
    receipt is marked failed rather than left `queued`, because a permanent
    "queued" with nothing on the stream is the state a polling client cannot
    escape: it would wait forever for work that was never sent.
    """
    if job_type not in JOB_NAME_FOR_KIND:
        raise ValueError(f"unknown_job_kind: {job_type}")

    resolved_id = job_id or str(uuid4())
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
        message = _publish_message(resolved_id, job_type, payload)
        await get_broker().kick(message)
    except Exception:
        await update_job_status(
            redis, resolved_id, STATUS_FAILED, error="job_publish_failed"
        )
        raise

    return resolved_id


async def update_job_status(
    redis: Redis,
    job_id: str,
    status: str,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    """Write one status transition, preserving the owner the receipt was created with.

    The owner is never taken from the caller here: it is the field the status route
    authorizes against, so allowing a worker to restate it would let a bug in a
    handler hand one learner's job to another.
    """
    raw = await redis.get(receipt_key(job_id))
    now = _now_iso()
    if raw:
        data = json.loads(raw)
    else:
        # A receipt that expired mid-flight is still updated, so the client sees a
        # terminal state instead of polling a key that will never come back. The
        # owner is absent, which the status route treats as "not yours".
        data = {"id": job_id, "createdAt": now, "owner_id": None}

    data["status"] = status
    data["updatedAt"] = now
    if result is not None:
        data["result"] = result
    if error is not None:
        data["errorCode"] = error
    if status in TERMINAL_STATUSES:
        data["finishedAt"] = now

    await redis.set(receipt_key(job_id), json.dumps(data), ex=RECEIPT_TTL_SECONDS)


async def read_receipt(redis: Redis, job_id: str) -> dict | None:
    raw = await redis.get(receipt_key(job_id))
    return json.loads(raw) if raw else None


__all__ = [
    "RECEIPT_TTL_SECONDS",
    "STATUS_DONE",
    "STATUS_EXPIRED",
    "STATUS_FAILED",
    "STATUS_QUEUED",
    "STATUS_RUNNING",
    "TASK_KIND_QUESTION_SUPPLY",
    "TASK_KIND_WORD",
    "TERMINAL_STATUSES",
    "enqueue_job",
    "read_receipt",
    "receipt_key",
    "update_job_status",
]
