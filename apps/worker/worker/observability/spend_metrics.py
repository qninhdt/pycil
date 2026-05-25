"""Structured per-job spend metrics emitted by worker jobs.

Sentry phase 15 reads breadcrumb category=spend; phase 15 daily Slack
report sums via the Redis counters. This module just emits the structured
log line so observability has a single shape.
"""
from __future__ import annotations

import logging
import time

_log = logging.getLogger("worker.spend")


def emit_spend(
    *,
    job_id: str,
    job_type: str,
    model_used: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cost_usd: float | None = None,
    duration_ms: float | None = None,
) -> None:
    """Log a single structured line. Sentry-friendly via 'extra'."""
    _log.info(
        "spend",
        extra={
            "job_id": job_id,
            "job_type": job_type,
            "model_used": model_used,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "duration_ms": duration_ms,
            "ts": time.time(),
        },
    )
