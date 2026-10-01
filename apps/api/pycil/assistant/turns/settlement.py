"""Settle completed assistant usage into the period captured at admission."""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pycil.assistant.turns.usage import TurnUsage, usage_units_for
from pycil.billing.ledger import record_usage
from pycil.billing.plans import FeatureKey
from pycil.billing.schemas import UsageSettlement
from pycil.platform.telemetry import record_assistant_zero_cost

logger = logging.getLogger(__name__)


def is_billable_status(status: str) -> bool:
    """Determine whether a terminal execution status is billed under current product policy.

    Completed, interrupted and disconnected segments bill completed model calls.
    Failed and cancelled segments remain free.
    """
    return status in {"completed", "interrupted", "disconnected"}


def audit_details_for_segment(
    usage: TurnUsage,
    *,
    run_id: str,
    status: str,
    segment: str,
    thread_id: str | None = None,
    interrupt_id: str | None = None,
    model_id: str | None = None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    """Capture diagnostic audit metadata for the settled assistant segment."""
    models_summary: dict[str, Any] = {}
    for call in usage.calls:
        models_summary[call.model_id] = {
            "input_tokens": call.input_tokens,
            "output_tokens": call.output_tokens,
            "cached_input_tokens": call.cached_input_tokens,
            "cache_write_tokens": call.cache_write_tokens,
            "rates": call.rates.to_dict(),
        }

    return {
        "run_id": run_id,
        "thread_id": thread_id,
        "segment": segment,
        "status": status,
        "interrupt_id": interrupt_id,
        "model_id": model_id,
        "reasoning_effort": reasoning_effort,
        "model_calls": usage.model_calls,
        "unmetered_calls": usage.unmetered_calls,
        "unpriced_cache_write_tokens": usage.unpriced_cache_write_tokens,
        "models": models_summary,
        "usage": usage.to_dict(),
    }


async def settle_assistant_segment(
    session: AsyncSession,
    *,
    user_id: UUID,
    period_id: UUID,
    occurred_at: datetime,
    event_key: str | None = None,
    run_id: str,
    status: str,
    usage: TurnUsage,
    interrupt_id: str | None = None,
    thread_id: str | None = None,
    model_id: str | None = None,
    reasoning_effort: str | None = None,
) -> UsageSettlement | None:
    """Settle reported usage under the server-generated key for this execution."""
    if not is_billable_status(status):
        logger.info(
            "assistant_segment_unbilled",
            extra={"run_id": run_id, "status": status, "reason": "unbillable_status"},
        )
        return None

    amount_units = usage_units_for(usage)
    if amount_units <= 0:
        record_assistant_zero_cost()
        logger.info(
            "assistant_segment_zero_cost",
            extra={"run_id": run_id, "status": status},
        )
        return None

    segment_name = "resume" if interrupt_id else "initial"
    if not event_key:
        event_key = f"assistant:{run_id}:{interrupt_id or 'initial'}"

    details = audit_details_for_segment(
        usage,
        run_id=run_id,
        status=status,
        segment=segment_name,
        thread_id=thread_id,
        interrupt_id=interrupt_id,
        model_id=model_id,
        reasoning_effort=reasoning_effort,
    )

    settlement = await record_usage(
        session,
        user_id=user_id,
        period_id=period_id,
        event_key=event_key,
        feature_key=FeatureKey.ASSISTANT,
        units=amount_units,
        occurred_at=occurred_at,
        details=details,
    )

    logger.info(
        "assistant_segment_settled",
        extra={
            "user_id": str(user_id),
            "period_id": str(period_id),
            "run_id": run_id,
            "event_key": event_key,
            "amount_units": amount_units,
            "status": status,
            "idempotent_replay": settlement.idempotent_replay,
        },
    )
    return settlement
