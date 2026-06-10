"""generate_question MCQ pipeline tests.

Pinned:
- Happy path: INSERT into questions, sanitize stem/options, mark job completed.
- Cache hit: pre-existing MCQ row → no LLM call.
- Definition not found → mark_failed.
- Sanitization: URLs in stem/options stripped (`sanitize_text`).
- `is_terminal` short-circuit returns `{"status": "duplicate"}`.
"""
from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from shared.questions import MCQData
from worker.jobs import generate_question as gq_mod
from worker.llm.openrouter import FallbackResult


def _canned_mcq() -> MCQData:
    return MCQData(
        stem="What is the meaning?",
        options=[
            "the actual meaning",
            "wrong distractor one",
            "wrong distractor two",
            "wrong distractor three",
        ],
        correct_index=0,
        explanation="Because the canonical meaning matches.",
        distractor_rationale=[
            "first distractor reasoning",
            "second distractor reasoning",
            "third distractor reasoning",
        ],
    )


def _canned_mcq_with_url() -> MCQData:
    return MCQData(
        stem="See https://leak.example for the answer.",
        options=[
            "go to https://leak.example/a",
            "wrong distractor one",
            "wrong distractor two",
            "wrong distractor three",
        ],
        correct_index=0,
        explanation="Per https://leak.example/explanation.",
        distractor_rationale=[
            "first distractor reasoning",
            "second distractor reasoning",
            "third distractor reasoning",
        ],
    )


@pytest.fixture
def llm_mcq_ok(monkeypatch):
    canned = _canned_mcq()

    async def fake(prompt, schema, **kwargs):
        return FallbackResult(
            output=canned, model_used="test", hops=0, elapsed_seconds=0.0
        )

    monkeypatch.setattr("worker.jobs.generate_question.invoke_with_fallback", fake)
    monkeypatch.setattr("worker.jobs.generate_question.render", lambda *a, **k: "P")


async def _seed_definition_and_job(session) -> tuple[int, str]:
    term = (
        await session.execute(
            text(
                "INSERT INTO terms (value, type) "
                "VALUES (:v, 'SINGLE_WORD'::term_type) RETURNING id"
            ),
            {"v": f"q-term-{uuid4().hex[:6]}"},
        )
    ).one()
    definition = (
        await session.execute(
            text(
                """
                INSERT INTO definitions (
                    term_id, cefr_level, part_of_speech,
                    synonyms, antonyms, notes, canonical_meaning
                )
                VALUES (
                    :tid, 'B1'::cefr_level, 'NOUN'::part_of_speech,
                    '{}', '{}', '{}', 'a meaning'
                )
                RETURNING id
                """
            ),
            {"tid": term.id},
        )
    ).one()
    job_id = str(uuid4())
    await session.execute(
        text(
            "INSERT INTO jobs (id, type, status, payload) "
            "VALUES (:id, 'generate_question', 'pending', '{}'::jsonb)"
        ),
        {"id": job_id},
    )
    await session.commit()
    return definition.id, job_id


async def test_generate_question_happy_inserts_row(
    session, arq_ctx, llm_mcq_ok
) -> None:
    def_id, job_id = await _seed_definition_and_job(session)

    result = await gq_mod.generate_question(arq_ctx, def_id, job_id)
    assert result == {"status": "completed"}

    row = (
        await session.execute(
            text(
                "SELECT id, type::text AS type, data FROM questions "
                "WHERE definition_id = :d"
            ),
            {"d": def_id},
        )
    ).one()
    assert row.type == "MULTIPLE_CHOICE"
    data = row.data if isinstance(row.data, dict) else json.loads(row.data)
    assert data["correct_index"] == 0
    assert len(data["options"]) == 4


async def test_generate_question_cache_hit_skips_llm(
    session, arq_ctx, monkeypatch
) -> None:
    """Pre-existing MCQ → mark completed without LLM call."""
    calls: list[str] = []

    async def fake(prompt, schema, **kwargs):
        calls.append("called")
        return FallbackResult(
            output=_canned_mcq(), model_used="test", hops=0, elapsed_seconds=0.0
        )

    monkeypatch.setattr("worker.jobs.generate_question.invoke_with_fallback", fake)
    monkeypatch.setattr("worker.jobs.generate_question.render", lambda *a, **k: "P")

    def_id, job_id = await _seed_definition_and_job(session)
    # Fill the bank to the default target depth (2) for the easy MCQ slot so the
    # depth-aware skip short-circuits before any LLM call.
    for _ in range(2):
        await session.execute(
            text(
                "INSERT INTO questions (definition_id, type, data) "
                "VALUES (:d, 'MULTIPLE_CHOICE'::question_type, "
                "'{\"difficulty\": \"easy\"}'::jsonb)"
            ),
            {"d": def_id},
        )
    await session.commit()

    result = await gq_mod.generate_question(arq_ctx, def_id, job_id)
    assert result["status"] == "completed"
    assert result["cache_hit"] is True
    assert calls == []


async def test_generate_question_definition_not_found(
    session, arq_ctx, llm_mcq_ok
) -> None:
    job_id = str(uuid4())
    await session.execute(
        text(
            "INSERT INTO jobs (id, type, status, payload) "
            "VALUES (:id, 'generate_question', 'pending', '{}'::jsonb)"
        ),
        {"id": job_id},
    )
    await session.commit()

    result = await gq_mod.generate_question(arq_ctx, 999_999, job_id)
    assert result == {"status": "failed"}

    row = (
        await session.execute(
            text("SELECT status, error FROM jobs WHERE id = :id"),
            {"id": job_id},
        )
    ).one()
    assert row.status == "failed"
    assert row.error == "definition_not_found"


async def test_mcq_sanitize_strips_urls(session, arq_ctx, monkeypatch) -> None:
    """Persisted MCQ data must NOT contain raw URLs in stem/options."""
    async def fake(prompt, schema, **kwargs):
        return FallbackResult(
            output=_canned_mcq_with_url(), model_used="test", hops=0, elapsed_seconds=0.0
        )

    monkeypatch.setattr("worker.jobs.generate_question.invoke_with_fallback", fake)
    monkeypatch.setattr("worker.jobs.generate_question.render", lambda *a, **k: "P")

    def_id, job_id = await _seed_definition_and_job(session)
    await gq_mod.generate_question(arq_ctx, def_id, job_id)

    row = (
        await session.execute(
            text("SELECT data FROM questions WHERE definition_id = :d"),
            {"d": def_id},
        )
    ).one()
    data = row.data if isinstance(row.data, dict) else json.loads(row.data)
    assert "https://" not in data["stem"]
    for opt in data["options"]:
        assert "https://" not in opt
    assert "https://" not in data["explanation"]


async def test_terminal_job_returns_duplicate(session, arq_ctx, monkeypatch) -> None:
    calls: list[str] = []

    async def fake(prompt, schema, **kwargs):
        calls.append("called")
        return FallbackResult(
            output=_canned_mcq(), model_used="test", hops=0, elapsed_seconds=0.0
        )

    monkeypatch.setattr("worker.jobs.generate_question.invoke_with_fallback", fake)
    monkeypatch.setattr("worker.jobs.generate_question.render", lambda *a, **k: "P")

    def_id, job_id = await _seed_definition_and_job(session)
    # Pre-mark job as terminal.
    await session.execute(
        text("UPDATE jobs SET status = 'completed' WHERE id = :id"),
        {"id": job_id},
    )
    await session.commit()

    result = await gq_mod.generate_question(arq_ctx, def_id, job_id)
    assert result == {"status": "duplicate"}
    assert calls == []
