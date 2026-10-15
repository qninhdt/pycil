"""Native CLI probes: the real process lifecycle, without provider calls."""

import asyncio

from taskiq import Context, TaskiqDepends

from pycil.app.broker import broker


@broker.task(task_name="test.worker_probe", timeout=5)
async def probe(key: str, delay: float, context: Context = TaskiqDepends()) -> str:
    redis = context.state.resources.redis
    await redis.incr(key)
    await asyncio.sleep(delay)
    return "finished"
