"""prewarm_questions budget gate (DB-free).

Pinned (red-team C3): when the daily OpenRouter spend cap is already reached,
prewarm short-circuits and enqueues nothing — no unattributed cap drain.
"""
from __future__ import annotations

import pytest
from shared.redis_lock import spend_key_today

from worker.config import get_settings
from worker.jobs.prewarm_questions import prewarm_questions


@pytest.mark.asyncio
async def test_prewarm_skips_when_over_budget(arq_ctx) -> None:
    redis = arq_ctx["redis"]
    cap = get_settings().openrouter_budget_daily_usd
    await redis.set(spend_key_today(), str(cap + 1.0))

    result = await prewarm_questions(
        arq_ctx, [1, 2, 3], user_id="00000000-0000-0000-0000-000000000001"
    )

    assert result["status"] == "skipped_budget"
    assert result["enqueued"] == 0
