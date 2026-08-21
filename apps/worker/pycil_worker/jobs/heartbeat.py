"""Publish a short worker heartbeat used by the API readiness probe."""

from shared.tasks.contract import WORKER_HEARTBEAT_KEY, WORKER_HEARTBEAT_TTL_SECONDS

from pycil_worker.context import ReadyWorkerContext


async def heartbeat(ctx: ReadyWorkerContext) -> dict:
    await ctx["redis"].setex(WORKER_HEARTBEAT_KEY, WORKER_HEARTBEAT_TTL_SECONDS, "1")
    return {"status": "ok"}
