"""LLM-as-judge service for tier-4 answer grading.

Synchronous httpx call to OpenRouter (Haiku) wrapped with:
- Redis result cache keyed by (definition_id, normalized_user_answer).
- Per-user daily call limit.
- Global daily USD budget cap.
- Strict yes/no/borderline parse with fallback to incorrect on parse failure.

All gates are short-circuit so disabled mode adds zero latency.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date
from typing import Literal

import httpx
from redis.asyncio import Redis

from pycil_core.config import get_settings

_log = logging.getLogger(__name__)
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
_ESTIMATED_COST_USD = 0.0001
_PROMPT_TEMPLATE = (
    "You are a strict vocabulary grader. Given a CANONICAL definition and a "
    "USER_ANSWER, decide if the user answer is semantically equivalent.\n\n"
    "CANONICAL:\n{canonical}\n\nUSER_ANSWER:\n{user_answer}\n\n"
    "Reply with exactly one word: yes, no, or borderline. Be strict — only "
    "say yes if the user answer captures the same meaning."
)

JudgeResult = Literal["correct", "borderline", "incorrect"]


def _cache_key(definition_id: int, normalized: str) -> str:
    h = hashlib.sha256(f"{definition_id}:{normalized}".encode()).hexdigest()[:32]
    return f"grade_cache:{h}"


def _user_counter_key(user_id: int) -> str:
    return f"rl:llm_judge:{user_id}:{date.today().isoformat()}"


def _budget_key() -> str:
    return f"openrouter:spend:judge:{date.today().isoformat()}"


def _parse_response(text: str) -> JudgeResult:
    head = re.split(r"[\s.,;:!?]", text.strip().lower(), maxsplit=1)[0]
    if head == "yes":
        return "correct"
    if head == "borderline":
        return "borderline"
    return "incorrect"


async def judge(
    *,
    redis: Redis,
    user_id: int,
    definition_id: int,
    canonical: str,
    user_answer: str,
    normalized: str,
) -> JudgeResult:
    settings = get_settings()
    if not settings.llm_judge_enabled or not settings.openrouter_api_key:
        return "incorrect"

    cache_key = _cache_key(definition_id, normalized)
    cached = await redis.get(cache_key)
    if cached is not None:
        return cached.decode() if isinstance(cached, bytes) else cached  # type: ignore[return-value]

    used = await redis.incr(_user_counter_key(user_id))
    if used == 1:
        await redis.expire(_user_counter_key(user_id), 60 * 60 * 25)
    if used > settings.llm_judge_per_user_daily_limit:
        return "incorrect"

    budget_used = await redis.get(_budget_key())
    if budget_used is not None:
        spent = float(budget_used) if not isinstance(budget_used, bytes) else float(budget_used)
        if spent >= settings.llm_judge_budget_daily_usd:
            return "incorrect"

    prompt = _PROMPT_TEMPLATE.format(canonical=canonical, user_answer=user_answer)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.llm_judge_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 8,
                    "temperature": 0.0,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        _log.warning("llm_judge_failed", extra={"err": str(exc)[:200]})
        return "incorrect"

    result = _parse_response(content)
    await redis.setex(cache_key, _CACHE_TTL_SECONDS, result)
    await redis.incrbyfloat(_budget_key(), _ESTIMATED_COST_USD)
    await redis.expire(_budget_key(), 60 * 60 * 25)
    return result
