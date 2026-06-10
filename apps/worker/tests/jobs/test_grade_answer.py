"""grade_answer LLM-judge gating (DB-free).

Pinned:
- _llm_judge returns None when disabled → caller keeps tier-1-3 verdict.
- _llm_judge returns None when over the daily budget cap (no LLM call).
"""
from __future__ import annotations

import pytest
from shared.redis_lock import spend_key_today

from worker.config import get_settings
from worker.jobs.grade_answer import _llm_judge


@pytest.mark.asyncio
async def test_llm_judge_disabled_returns_none(arq_ctx, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_judge_enabled", False)
    result = await _llm_judge(arq_ctx["redis"], "a feline", "cat")
    assert result is None


@pytest.mark.asyncio
async def test_llm_judge_over_budget_returns_none(arq_ctx, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_judge_enabled", True)
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    redis = arq_ctx["redis"]
    await redis.set(spend_key_today(), str(settings.openrouter_budget_daily_usd + 1))

    result = await _llm_judge(redis, "a feline", "cat")
    assert result is None
