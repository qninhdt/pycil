"""ACK-aware relay for persisted async-task snapshots.

Rows are leased before publication and acknowledged only after Centrifugo's HTTP
API accepts the command. A crash after acceptance intentionally republishes the
same event/version on the next sweep.
"""

import logging

import httpx
from pycil.config import settings
from pycil.tasks.application import service

logger = logging.getLogger(__name__)


async def dispatch_task_outbox(ctx: dict) -> dict[str, int]:
    lease_owner = f"{ctx['worker_id']}:task-outbox"
    published = retried = dead_letters = 0
    async with ctx["session_factory"]() as session:
        rows = await service.claim_outbox_batch(session, lease_owner)
    async with httpx.AsyncClient(timeout=5.0) as client:
        for row in rows:
            try:
                response = await client.post(
                    f"{settings.centrifugo_url}/api/publish",
                    headers={"X-API-Key": settings.centrifugo_api_key},
                    json={"channel": row.channel, "data": row.payload},
                )
                response.raise_for_status()
                if response.json().get("error"):
                    raise RuntimeError("centrifugo_command_rejected")
            except (httpx.HTTPError, ValueError, RuntimeError):
                async with ctx["session_factory"]() as session:
                    updated = await service.retry_outbox(session, row.id, lease_owner)
                if updated is not None and updated.status.value == "dead_letter":
                    dead_letters += 1
                    logger.error(
                        "async task outbox delivery exhausted", extra={"outbox_id": str(row.id)}
                    )
                else:
                    retried += 1
            else:
                async with ctx["session_factory"]() as session:
                    acknowledged = await service.acknowledge_outbox(session, row.id, lease_owner)
                published += int(acknowledged is not None)
    return {"published": published, "retried": retried, "deadLetters": dead_letters}
