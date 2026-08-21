"""ACK-aware relay for persisted async-task snapshots.

Rows are leased before publication and acknowledged only after Centrifugo's HTTP
API accepts the command. A crash after acceptance intentionally republishes the
same event/version on the next sweep.
"""

import logging

import httpx
from pycil.tasks.application import service

from pycil_worker.context import ReadyWorkerContext

logger = logging.getLogger(__name__)


async def dispatch_task_outbox(ctx: ReadyWorkerContext) -> dict[str, int]:
    lease_owner = f"{ctx['worker_id']}:task-outbox"
    published = retried = dead_letters = 0
    async with ctx["session_factory"]() as session:
        rows = await service.claim_outbox_batch(session, lease_owner)
    for row in rows:
        # Adapter reuse: publication rides the one process-wide broker client, so
        # headers, timeout and command-error checking live only in the ports module.
        try:
            await ctx["centrifugo"].publish(row.channel, row.payload)
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
