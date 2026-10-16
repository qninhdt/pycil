"""Asyncio concurrency primitives and cancellation-safe thread offloading."""

import asyncio
from collections.abc import Callable


async def shielded_to_thread[T](call: Callable[[], T]) -> T:
    """Run blocking synchronous work off-loop and join it on cancellation safely."""
    task = asyncio.create_task(asyncio.to_thread(call))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise
