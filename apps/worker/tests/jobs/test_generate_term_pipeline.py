"""Happy-path + cache-hit + retry semantics for `generate_term`.

`worker.llm.openrouter.invoke_with_fallback` is monkeypatched per-test —
no network egress. `worker.prompts.render` is patched to a stub since
the real Jinja templates are not in scope of this test.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text

from worker.jobs import generate_term as gt_mod
from worker.llm.openrouter import FallbackResult
from worker.schemas.term_generation import (
    GeneratedDefinition,
    GeneratedExample,
    GeneratedParaphrase,
    PartOfSpeech,
    TermGenerationOutput,
)


def _canned_output() -> TermGenerationOutput:
    return TermGenerationOutput(
        definition=GeneratedDefinition(
            part_of_speech=PartOfSpeech.NOUN,
            cefr_level="B1",
            canonical_meaning="a canonical test meaning",
            synonyms=["alt"],
            antonyms=[],
        ),
        paraphrases=[
            GeneratedParaphrase(value="another way to say it", cefr_level="B1"),
            GeneratedParaphrase(value="yet another phrasing", cefr_level="A2"),
        ],
        examples=[
            GeneratedExample(value="An example sentence here.", cefr_level="A2"),
            GeneratedExample(value="A second example sentence.", cefr_level="B1"),
        ],
    )


@pytest.fixture
def llm_calls(monkeypatch):
    calls: list[str] = []

    async def fake(prompt, schema, **kwargs):
        calls.append(prompt)
        return FallbackResult(
            output=_canned_output(), model_used="test", hops=0, elapsed_seconds=0.0
        )

    monkeypatch.setattr("worker.jobs.generate_term.invoke_with_fallback", fake)
    monkeypatch.setattr("worker.jobs.generate_term.render", lambda *a, **k: "PROMPT")
    return calls


async def _seed_term_and_job(session, *, value: str = "happy-term") -> tuple[int, str]:
    row = (
        await session.execute(
            text(
                "INSERT INTO terms (value, type) "
                "VALUES (:v, 'SINGLE_WORD'::term_type) RETURNING id"
            ),
            {"v": value},
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
    return row.id, job_id


async def test_generate_term_happy_path(session, arq_ctx, llm_calls) -> None:
    term_id, job_id = await _seed_term_and_job(session)

    result = await gt_mod.generate_term(arq_ctx, term_id, job_id)

    assert result == {"status": "completed"}
    assert len(llm_calls) == 1

    # Definition row inserted.
    def_row = (
        await session.execute(
            text(
                "SELECT id, canonical_meaning, part_of_speech::text AS pos "
                "FROM definitions WHERE term_id = :tid"
            ),
            {"tid": term_id},
        )
    ).one()
    assert "canonical test meaning" in def_row.canonical_meaning
    assert def_row.pos == "NOUN"

    # Job marked completed.
    job_row = (
        await session.execute(
            text("SELECT status, result FROM jobs WHERE id = :id"),
            {"id": job_id},
        )
    ).one()
    assert job_row.status == "completed"


async def test_generate_term_cache_hit_skips_llm(
    session, arq_ctx, llm_calls
) -> None:
    """If `definitions(term_id)` already exists, `_invoke_llm` must NOT fire."""
    term_id, job_id = await _seed_term_and_job(session, value="cached-term")

    # Pre-INSERT a definition for this term.
    await session.execute(
        text(
            """
            INSERT INTO definitions (
                term_id, cefr_level, part_of_speech,
                synonyms, antonyms, notes, canonical_meaning
            )
            VALUES (
                :tid, 'B1'::cefr_level, 'NOUN'::part_of_speech,
                '{}', '{}', '{}', 'pre-existing'
            )
            """
        ),
        {"tid": term_id},
    )
    await session.commit()

    result = await gt_mod.generate_term(arq_ctx, term_id, job_id)

    assert result["status"] == "completed"
    assert result["cache_hit"] is True
    assert llm_calls == []  # no LLM call


async def test_generate_term_term_not_found(session, arq_ctx, llm_calls) -> None:
    job_id = str(uuid4())
    await session.execute(
        text(
            "INSERT INTO jobs (id, type, status, payload) "
            "VALUES (:id, 'generate_term', 'pending', '{}'::jsonb)"
        ),
        {"id": job_id},
    )
    await session.commit()

    result = await gt_mod.generate_term(arq_ctx, 999_999, job_id)

    assert result == {"status": "failed"}
    job_row = (
        await session.execute(
            text("SELECT status, error FROM jobs WHERE id = :id"),
            {"id": job_id},
        )
    ).one()
    assert job_row.status == "failed"
    assert job_row.error == "term_not_found"
    assert llm_calls == []


async def test_generate_term_validation_retry(session, arq_ctx, monkeypatch) -> None:
    """First LLM call raises ValidationError; second (with `_RETRY_SUFFIX`) succeeds."""
    from pydantic import ValidationError

    calls: list[str] = []

    async def fake(prompt, schema, **kwargs):
        calls.append(prompt)
        if len(calls) == 1:
            try:
                schema.model_validate({"definition": None})
            except ValidationError as e:
                raise e
        return FallbackResult(
            output=_canned_output(), model_used="test", hops=0, elapsed_seconds=0.0
        )

    monkeypatch.setattr("worker.jobs.generate_term.invoke_with_fallback", fake)
    monkeypatch.setattr("worker.jobs.generate_term.render", lambda *a, **k: "PROMPT")

    term_id, job_id = await _seed_term_and_job(session, value="retry-term")
    result = await gt_mod.generate_term(arq_ctx, term_id, job_id)

    assert result == {"status": "completed"}
    assert len(calls) == 2
    # Second prompt has the strict-JSON suffix appended.
    assert "RETURN ONLY VALID JSON" in calls[1]


async def test_generate_term_two_strikes_failed_marks_terminal(
    session, fakeredis_client, monkeypatch
) -> None:
    """If both attempts fail AND `job_try == max_tries`, the job row is `failed`."""
    async def always_fail(prompt, schema, **kwargs):
        raise ValueError("malformed-output")

    monkeypatch.setattr("worker.jobs.generate_term.invoke_with_fallback", always_fail)
    monkeypatch.setattr("worker.jobs.generate_term.render", lambda *a, **k: "PROMPT")

    term_id, job_id = await _seed_term_and_job(session, value="two-strikes")

    ctx = {"redis": fakeredis_client, "job_try": 3, "max_tries": 3}
    with pytest.raises(ValueError):
        await gt_mod.generate_term(ctx, term_id, job_id)

    job_row = (
        await session.execute(
            text("SELECT status FROM jobs WHERE id = :id"),
            {"id": job_id},
        )
    ).one()
    assert job_row.status == "failed"


async def test_generate_term_non_terminal_attempt_reraises_without_failed(
    session, fakeredis_client, monkeypatch
) -> None:
    """`job_try < max_tries` → exception propagates BUT job is NOT marked failed."""
    async def always_fail(prompt, schema, **kwargs):
        raise ValueError("transient")

    monkeypatch.setattr("worker.jobs.generate_term.invoke_with_fallback", always_fail)
    monkeypatch.setattr("worker.jobs.generate_term.render", lambda *a, **k: "PROMPT")

    term_id, job_id = await _seed_term_and_job(session, value="transient")

    ctx = {"redis": fakeredis_client, "job_try": 1, "max_tries": 3}
    with pytest.raises(ValueError):
        await gt_mod.generate_term(ctx, term_id, job_id)

    job_row = (
        await session.execute(
            text("SELECT status FROM jobs WHERE id = :id"),
            {"id": job_id},
        )
    ).one()
    # Still in flight: status is whatever it was before (pending), NOT failed.
    assert job_row.status != "failed"
