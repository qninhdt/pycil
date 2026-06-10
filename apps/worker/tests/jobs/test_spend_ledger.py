"""Persistent spend-ledger tests for the worker hot path (Phase 3).

Pins (red-team-driven):
- successful generate_question inserts exactly one llm_spend_events row with
  correct cost_usd/model and the job's created_by_user_id.
- cache-hit path inserts NO row.
- fault injection: ledger insert raises → generation still completes
  (jobs.status=completed), no exception propagates (dedicated session, F1).
- retry idempotency: a second invocation with the same job_id does not
  double-count (ON CONFLICT job_id, F12).
- generate_term records user_id=NULL (global cache, F10).
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text

from shared.questions import MCQData
from worker.jobs import generate_question as gq_mod
from worker.jobs import generate_term as gt_mod
from worker.llm.openrouter import FallbackResult
from worker.schemas.term_generation import (
    GeneratedDefinition,
    GeneratedExample,
    GeneratedParaphrase,
    PartOfSpeech,
    TermGenerationOutput,
)


def _canned_mcq() -> MCQData:
    return MCQData(
        stem="What is the meaning?",
        options=["right", "w1", "w2", "w3"],
        correct_index=0,
        explanation="because.",
        distractor_rationale=["a", "b", "c"],
    )


def _canned_term() -> TermGenerationOutput:
    return TermGenerationOutput(
        definition=GeneratedDefinition(
            part_of_speech=PartOfSpeech.NOUN,
            cefr_level="B1",
            canonical_meaning="canonical meaning",
            synonyms=[],
            antonyms=[],
        ),
        paraphrases=[
            GeneratedParaphrase(value="paraphrase one", cefr_level="B1"),
            GeneratedParaphrase(value="paraphrase two", cefr_level="A2"),
        ],
        examples=[
            GeneratedExample(value="An example.", cefr_level="A2"),
            GeneratedExample(value="A second example.", cefr_level="B1"),
        ],
    )


@pytest.fixture
def llm_mcq_ok(monkeypatch):
    async def fake(prompt, schema, **kwargs):
        return FallbackResult(
            output=_canned_mcq(), model_used="test-model", hops=0, elapsed_seconds=0.0
        )

    monkeypatch.setattr("worker.jobs.generate_question.invoke_with_fallback", fake)
    monkeypatch.setattr("worker.jobs.generate_question.render", lambda *a, **k: "P")


@pytest.fixture
def llm_term_ok(monkeypatch):
    async def fake(prompt, schema, **kwargs):
        return FallbackResult(
            output=_canned_term(), model_used="term-model", hops=0, elapsed_seconds=0.0
        )

    monkeypatch.setattr("worker.jobs.generate_term.invoke_with_fallback", fake)
    monkeypatch.setattr("worker.jobs.generate_term.render", lambda *a, **k: "P")


async def _seed_user(session) -> str:
    row = (
        await session.execute(
            text(
                "INSERT INTO users (email, name) "
                "VALUES (:e, 'Spender') RETURNING id"
            ),
            {"e": f"spend-{uuid4().hex[:8]}@example.com"},
        )
    ).one()
    await session.commit()
    return str(row.id)


async def _seed_def_and_job(session, *, owner_id: str | None) -> tuple[int, str]:
    term = (
        await session.execute(
            text(
                "INSERT INTO terms (value, type) "
                "VALUES (:v, 'SINGLE_WORD'::term_type) RETURNING id"
            ),
            {"v": f"sp-{uuid4().hex[:6]}"},
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
                VALUES (:tid, 'B1'::cefr_level, 'NOUN'::part_of_speech,
                        '{}', '{}', '{}', 'm')
                RETURNING id
                """
            ),
            {"tid": term.id},
        )
    ).one()
    job_id = str(uuid4())
    await session.execute(
        text(
            "INSERT INTO jobs (id, type, status, payload, created_by_user_id) "
            "VALUES (:id, 'generate_question', 'pending', '{}'::jsonb, "
            "CAST(:owner AS uuid))"
        ),
        {"id": job_id, "owner": owner_id},
    )
    await session.commit()
    return definition.id, job_id


async def _ledger_rows(session, job_id: str) -> list:
    return (
        await session.execute(
            text(
                "SELECT user_id, job_type, model, cost_usd "
                "FROM llm_spend_events WHERE job_id = CAST(:j AS uuid)"
            ),
            {"j": job_id},
        )
    ).all()


async def test_generate_question_inserts_one_ledger_row(
    session, arq_ctx, llm_mcq_ok
) -> None:
    owner = await _seed_user(session)
    def_id, job_id = await _seed_def_and_job(session, owner_id=owner)

    await gq_mod.generate_question(arq_ctx, def_id, job_id)

    rows = await _ledger_rows(session, job_id)
    assert len(rows) == 1
    assert str(rows[0].user_id) == owner
    assert rows[0].job_type == "generate_question"
    assert rows[0].model == "test-model"
    assert float(rows[0].cost_usd) == pytest.approx(gq_mod._ESTIMATED_COST_USD, rel=1e-6)


async def test_question_cache_hit_inserts_no_ledger_row(
    session, arq_ctx, llm_mcq_ok
) -> None:
    def_id, job_id = await _seed_def_and_job(session, owner_id=None)
    # Fill the bank to the default target depth (2) for the easy MCQ slot so the
    # depth-aware skip short-circuits before any LLM call or ledger write.
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

    await gq_mod.generate_question(arq_ctx, def_id, job_id)
    assert await _ledger_rows(session, job_id) == []


async def test_ledger_failure_does_not_break_generation(
    session, arq_ctx, llm_mcq_ok, monkeypatch
) -> None:
    """A ledger insert blowing up must NOT roll back a completed generation.

    Fault is injected at the DB layer INSIDE record_spend_event (its dedicated
    session). The internal try/except swallows it; generation completes (F1).
    """

    class _BoomSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, *a, **k):
            raise RuntimeError("ledger insert down")

        async def commit(self):  # pragma: no cover - never reached
            return None

    monkeypatch.setattr(
        "worker.observability.spend_ledger.SessionLocal",
        lambda: _BoomSession(),
    )

    owner = await _seed_user(session)
    def_id, job_id = await _seed_def_and_job(session, owner_id=owner)

    result = await gq_mod.generate_question(arq_ctx, def_id, job_id)
    assert result == {"status": "completed"}

    job = (
        await session.execute(
            text("SELECT status FROM jobs WHERE id = CAST(:j AS uuid)"),
            {"j": job_id},
        )
    ).one()
    assert job.status == "completed"
    # Question persisted despite ledger failure.
    q = (
        await session.execute(
            text("SELECT COUNT(*) AS c FROM questions WHERE definition_id = :d"),
            {"d": def_id},
        )
    ).one()
    assert q.c == 1
    # No ledger row was written (insert failed and was swallowed).
    assert await _ledger_rows(session, job_id) == []


async def test_retry_does_not_double_count(session, arq_ctx, llm_mcq_ok) -> None:
    """Re-invoking with the same job_id dedups via ON CONFLICT (job_id)."""
    owner = await _seed_user(session)
    def_id, job_id = await _seed_def_and_job(session, owner_id=owner)

    await gq_mod.generate_question(arq_ctx, def_id, job_id)
    # Second call: question already exists → cache-hit path (no new row anyway),
    # so directly exercise the ledger idempotency with a duplicate insert.
    from worker.observability.spend_ledger import record_spend_event

    await record_spend_event(
        user_id=owner,
        job_id=job_id,
        job_type="generate_question",
        model="dupe",
        cost_usd=999.0,
    )
    rows = await _ledger_rows(session, job_id)
    assert len(rows) == 1
    assert rows[0].model == "test-model"  # original row preserved


async def test_generate_term_records_null_user(
    session, arq_ctx, llm_term_ok
) -> None:
    term = (
        await session.execute(
            text(
                "INSERT INTO terms (value, type) "
                "VALUES (:v, 'SINGLE_WORD'::term_type) RETURNING id"
            ),
            {"v": f"t-{uuid4().hex[:6]}"},
        )
    ).one()
    job_id = str(uuid4())
    await session.execute(
        text(
            "INSERT INTO jobs (id, type, status, payload) "
            "VALUES (:id, 'generate_term', 'pending', '{}'::jsonb)"
        ),
        {"id": job_id},
    )
    await session.commit()

    await gt_mod.generate_term(arq_ctx, term.id, job_id)

    rows = await _ledger_rows(session, job_id)
    assert len(rows) == 1
    assert rows[0].user_id is None
    assert rows[0].job_type == "generate_term"
