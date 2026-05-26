"""Cost-tracking + sanitization invariants on `generate_term` / `generate_question`.

Pins:
- Happy-path runs increment `openrouter:spend:<UTC-day>` by exactly `_ESTIMATED_COST_USD`.
- Cache-hit path does NOT call `add_spend` (zero increment).
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text

from shared.redis_lock import spend_key_today
from worker.jobs import generate_term as gt_mod
from worker.schemas.term_generation import (
    GeneratedDefinition,
    GeneratedExample,
    GeneratedParaphrase,
    PartOfSpeech,
    TermGenerationOutput,
)


def _canned() -> TermGenerationOutput:
    return TermGenerationOutput(
        definition=GeneratedDefinition(
            part_of_speech=PartOfSpeech.NOUN,
            cefr_level="B1",
            canonical_meaning="canonical example meaning",
            synonyms=[],
            antonyms=[],
        ),
        paraphrases=[
            GeneratedParaphrase(value="paraphrase one", cefr_level="B1"),
            GeneratedParaphrase(value="paraphrase two", cefr_level="A2"),
        ],
        examples=[
            GeneratedExample(value="An example sentence here.", cefr_level="A2"),
            GeneratedExample(value="A second example.", cefr_level="B1"),
        ],
    )


@pytest.fixture
def llm_ok(monkeypatch):
    async def fake(prompt, schema):
        return _canned()

    monkeypatch.setattr("worker.jobs.generate_term.generate_with_schema", fake)
    monkeypatch.setattr("worker.jobs.generate_term.render", lambda *a, **k: "P")


async def _seed_job(session, *, term_value: str) -> tuple[int, str]:
    row = (
        await session.execute(
            text(
                "INSERT INTO terms (value, type) "
                "VALUES (:v, 'SINGLE_WORD'::term_type) RETURNING id"
            ),
            {"v": term_value},
        )
    ).one()
    jid = str(uuid4())
    await session.execute(
        text(
            "INSERT INTO jobs (id, type, status, payload) "
            "VALUES (:id, 'generate_term', 'pending', '{}'::jsonb)"
        ),
        {"id": jid},
    )
    await session.commit()
    return row.id, jid


async def test_happy_run_increments_daily_spend(
    session, fakeredis_client, arq_ctx, llm_ok
) -> None:
    term_id, job_id = await _seed_job(session, term_value="cost-happy")

    pre = await fakeredis_client.get(spend_key_today())
    await gt_mod.generate_term(arq_ctx, term_id, job_id)
    post = await fakeredis_client.get(spend_key_today())

    assert pre is None
    assert float(post) == pytest.approx(gt_mod._ESTIMATED_COST_USD, rel=1e-6)


async def test_cache_hit_skips_spend(
    session, fakeredis_client, arq_ctx, llm_ok
) -> None:
    term_id, job_id = await _seed_job(session, term_value="cost-cache")

    # Pre-INSERT a definition → cache hit branch.
    await session.execute(
        text(
            """
            INSERT INTO definitions (
                term_id, cefr_level, part_of_speech,
                synonyms, antonyms, notes, canonical_meaning
            )
            VALUES (
                :tid, 'B1'::cefr_level, 'NOUN'::part_of_speech,
                '{}', '{}', '{}', 'cached'
            )
            """
        ),
        {"tid": term_id},
    )
    await session.commit()

    await gt_mod.generate_term(arq_ctx, term_id, job_id)

    # add_spend never fired → key never created.
    assert await fakeredis_client.get(spend_key_today()) is None
