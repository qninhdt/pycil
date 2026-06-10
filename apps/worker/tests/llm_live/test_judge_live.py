"""Live contract: the LLM-judge verdict mapping against a real model.

Exercises `grade_answer._llm_judge` directly (the tier-4 semantic grader)
with the judge enabled and a fakeredis spend counter. Proves the real model
maps a semantically-equivalent answer to True and a clearly-wrong answer to
False. Skipped unless RUN_LLM_LIVE=1 (see conftest).
"""
from __future__ import annotations

import fakeredis.aioredis
import pytest

from worker.jobs.grade_answer import _llm_judge

pytestmark = pytest.mark.llm_live


@pytest.fixture
def _judge_redis():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def _noop() -> None:
        return None

    r.aclose = _noop  # type: ignore[method-assign]
    return r


@pytest.fixture(autouse=True)
def _enable_judge(monkeypatch):
    """Turn the budget-gated judge on for these tests."""
    monkeypatch.setenv("LLM_JUDGE_ENABLED", "true")
    from worker.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_judge_accepts_semantic_equivalent(_judge_redis) -> None:
    verdict = await _llm_judge(
        _judge_redis,
        canonical="lasting for a very short time; transient",
        user_answer="something that does not last long",
    )
    assert verdict is True


async def test_judge_rejects_clearly_wrong(_judge_redis) -> None:
    verdict = await _llm_judge(
        _judge_redis,
        canonical="lasting for a very short time; transient",
        user_answer="an extremely heavy metal object",
    )
    assert verdict is False
