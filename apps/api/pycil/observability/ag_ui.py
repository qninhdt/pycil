"""Measure native AG-UI terminal events without inspecting their content."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing
from time import perf_counter

from ag_ui.core import BaseEvent, EventType, RunFinishedEvent

from pycil.observability import get_logger, record_operation_duration

logger = get_logger(__name__)


async def observed_agent_events(
    events: AsyncGenerator[BaseEvent], *, name: str
) -> AsyncGenerator[BaseEvent]:
    started = perf_counter()
    outcome: str | None = None
    try:
        async with aclosing(events):
            async for event in events:
                if event.type == EventType.RUN_ERROR:
                    outcome = "failed"
                elif isinstance(event, RunFinishedEvent) and outcome != "failed":
                    reason = event.outcome.type if event.outcome is not None else "success"
                    outcome = {
                        "success": "succeeded",
                        "interrupt": "interrupted",
                        "cancelled": "cancelled",
                    }[reason]
                yield event
    except asyncio.CancelledError, GeneratorExit:
        outcome = outcome or "cancelled"
        raise
    except BaseException:
        outcome = "failed"
        raise
    finally:
        duration = perf_counter() - started
        outcome = outcome or "failed"
        record_operation_duration(name, duration, outcome)
        logger.info(
            "operation_completed",
            operation=name,
            outcome=outcome,
            duration_ms=round(duration * 1000, 2),
        )
