"""grade_answer arq job — async (LLM-judge) grading, verdict only.

Pipeline (mirrors generate_question):
  1. is_terminal pre-check (retry guard — never re-bill the LLM).
  2. Load the pending `responses` row + its question `data`.
  3. Tier 1-3: the plugin's own `check_answer` (exact/normalized match).
  4. Tier 4 (optional): worker-side LLM judge, budget-gated. Disabled → tier-1-3
     verdict stands.
  5. Persist verdict to the `responses` row (is_correct/grade_*); set
     grade_status='graded'. Leave elo_applied=FALSE — ELO/XP is applied later by
     learning_service.apply_async_verdict under the session lock.
  6. commit_terminal, then publish on results:job_{job_id}.

NEVER touches session Redis state, ELO, or XP — those need the session lock the
worker does not hold (see phase-04 deferred-ELO decision).
"""
from __future__ import annotations

import json
import logging

import httpx
from sqlalchemy import text

from shared.questions import registry
from worker.config import get_settings
from worker.db import SessionLocal
from worker.jobs.lifecycle import commit_terminal, is_terminal, publish_status
from worker.redis_helpers import add_spend, get_spend_daily

_log = logging.getLogger(__name__)
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_ESTIMATED_COST_USD = 0.0001
_PROMPT_TEMPLATE = (
    "You are a strict vocabulary grader. Given a CANONICAL answer and a "
    "USER_ANSWER, decide if the user answer is semantically equivalent.\n\n"
    "CANONICAL:\n{canonical}\n\nUSER_ANSWER:\n{user_answer}\n\n"
    "Reply with exactly one word: yes, no, or borderline."
)


async def _llm_judge(redis, canonical: str, user_answer: str) -> bool | None:
    """Worker-side LLM judge. Returns True/False, or None when unavailable
    (disabled, no key, over budget, or call failure) so the caller keeps the
    tier-1-3 verdict."""
    settings = get_settings()
    if not settings.llm_judge_enabled or not settings.openrouter_api_key:
        return None
    if await get_spend_daily(redis) >= settings.openrouter_budget_daily_usd:
        return None
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
        _log.warning("grade_answer_llm_judge_failed", extra={"err": str(exc)[:200]})
        return None
    await add_spend(redis, _ESTIMATED_COST_USD)
    head = content.strip().lower().split()[0] if content.strip() else "no"
    if head == "yes":
        return True
    if head == "borderline":
        return True
    return False


async def grade_answer(ctx: dict, job_id: str, response_id: str) -> dict:
    """arq entrypoint: grade a pending free-text response, publish the verdict."""
    redis = ctx["redis"]

    async with SessionLocal() as gate:
        if await is_terminal(gate, job_id):
            return {"status": "duplicate"}

    async with SessionLocal() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT r.user_answer, q.type::text AS type, q.data
                      FROM responses r
                      JOIN questions q ON q.id = r.question_id
                     WHERE r.id = :rid
                    """
                ),
                {"rid": response_id},
            )
        ).first()
        if row is None:
            await commit_terminal(
                session, job_id=job_id, status="failed", error="response_not_found"
            )
            await publish_status(
                redis, f"results:job_{job_id}",
                {"status": "failed", "error": "response_not_found"},
            )
            return {"status": "failed"}

        data = row.data
        if isinstance(data, str):
            data = json.loads(data)
        user_answer = row.user_answer or ""

        # Tier 1-3: plugin's own exact/normalized match.
        correct = False
        feedback = None
        if registry.is_registered(row.type):
            check = registry.get(row.type).check_answer(
                data, {"user_answer": user_answer}
            )
            correct = check.correct
            feedback = check.feedback

        # Tier 4: LLM judge only if the cheap tiers missed.
        if not correct:
            canonical = str(data.get("expected_answer") or "")
            verdict = await _llm_judge(redis, canonical, user_answer)
            if verdict is True:
                correct = True

        score = 1.0 if correct else 0.0
        await session.execute(
            text(
                """
                UPDATE responses
                   SET is_correct = :ic, grade_status = 'graded',
                       grade_score = :sc, grade_feedback = :fb
                 WHERE id = :rid
                """
            ),
            {"ic": correct, "sc": score, "fb": feedback, "rid": response_id},
        )
        result = {"correct": correct, "score": score, "feedback": feedback,
                  "response_id": response_id}
        committed = await commit_terminal(
            session, job_id=job_id, status="completed", result=result
        )
        if not committed:
            return {"status": "duplicate"}
        await publish_status(
            redis, f"results:job_{job_id}", {"status": "completed", **result}
        )
        return {"status": "completed"}
