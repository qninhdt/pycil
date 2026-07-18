"""Publish a short worker heartbeat used by the API readiness probe."""

_HEARTBEAT_KEY = "worker:heartbeat"
_HEARTBEAT_TTL_SECONDS = 90


async def heartbeat(ctx: dict) -> dict:
    await ctx["redis"].setex(_HEARTBEAT_KEY, _HEARTBEAT_TTL_SECONDS, "1")
    return {"status": "ok"}
