"""translate_definition + tts_render job pipelines.

Both jobs were touched by the raw-SQL→SQLModel conversion and had no tests,
so the converted multi-column `select(...)` read-path and the
`is_terminal` / `commit_terminal` lifecycle helpers were unverified here.

Pinned:
- Happy path commits terminal `completed` + publishes after commit.
- `definition_not_found` → terminal `failed`.
- `is_terminal` short-circuit returns `{"status": "duplicate"}` (depends on
  the lifecycle `select(Job.status)` scalarization fix).
- tts `tts_not_configured` guard when env missing.
"""
from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from worker.jobs import translate_definition as tr_mod
from worker.jobs import tts_render as tts_mod


async def _seed_definition_and_job(
    session, *, job_type: str, canonical: str = "a canonical meaning"
) -> tuple[int, str]:
    term = (
        await session.execute(
            text(
                "INSERT INTO terms (value, type) "
                "VALUES (:v, 'SINGLE_WORD'::term_type) RETURNING id"
            ),
            {"v": f"tt-term-{uuid4().hex[:6]}"},
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
                    '{}', '{}', '{}', :canon
                )
                RETURNING id
                """
            ),
            {"tid": term.id, "canon": canonical},
        )
    ).one()
    job_id = str(uuid4())
    await session.execute(
        text(
            "INSERT INTO jobs (id, type, status, payload) "
            "VALUES (:id, :t, 'pending', '{}'::jsonb)"
        ),
        {"id": job_id, "t": job_type},
    )
    await session.commit()
    return definition.id, job_id


# --------------------------------------------------------------------------
# translate_definition
# --------------------------------------------------------------------------


@pytest.fixture
def translate_ok(monkeypatch):
    async def fake(prompt, schema):
        return schema(
            canonical_translated="la traduction canonique",
            paraphrases_translated=[],
            examples_translated=[],
        )

    monkeypatch.setattr(
        "worker.jobs.translate_definition.generate_with_schema", fake
    )
    monkeypatch.setattr(
        "worker.jobs.translate_definition.render", lambda *a, **k: "PROMPT"
    )


async def test_translate_happy_writes_jsonb(
    session, arq_ctx, fakeredis_client, translate_ok
) -> None:
    def_id, job_id = await _seed_definition_and_job(
        session, job_type="translate_definition"
    )

    result = await tr_mod.translate_definition(arq_ctx, def_id, "fr", job_id)
    assert result["status"] == "completed"

    row = (
        await session.execute(
            text("SELECT translation FROM definitions WHERE id = :id"),
            {"id": def_id},
        )
    ).one()
    translation = row.translation if isinstance(row.translation, dict) else json.loads(row.translation)
    assert translation["fr"] == "la traduction canonique"

    job_row = (
        await session.execute(
            text("SELECT status FROM jobs WHERE id = :id"), {"id": job_id}
        )
    ).one()
    assert job_row.status == "completed"


async def test_translate_definition_not_found(session, arq_ctx, translate_ok) -> None:
    job_id = str(uuid4())
    await session.execute(
        text(
            "INSERT INTO jobs (id, type, status, payload) "
            "VALUES (:id, 'translate_definition', 'pending', '{}'::jsonb)"
        ),
        {"id": job_id},
    )
    await session.commit()

    result = await tr_mod.translate_definition(arq_ctx, 999_999, "fr", job_id)
    assert result["status"] == "failed"

    job_row = (
        await session.execute(
            text("SELECT status, error FROM jobs WHERE id = :id"), {"id": job_id}
        )
    ).one()
    assert job_row.status == "failed"
    assert job_row.error == "definition_not_found"


async def test_translate_terminal_returns_duplicate(
    session, arq_ctx, translate_ok
) -> None:
    """is_terminal gate: pre-completed job must short-circuit (lifecycle fix)."""
    def_id, job_id = await _seed_definition_and_job(
        session, job_type="translate_definition"
    )
    await session.execute(
        text("UPDATE jobs SET status = 'completed' WHERE id = :id"), {"id": job_id}
    )
    await session.commit()

    result = await tr_mod.translate_definition(arq_ctx, def_id, "fr", job_id)
    assert result == {"status": "duplicate"}


async def test_translate_llm_failure_last_attempt_marks_failed(
    session, fakeredis_client, monkeypatch
) -> None:
    """LLM raises on the final attempt → job terminal `failed`, re-raised."""
    async def boom(prompt, schema):
        raise ValueError("llm-down")

    monkeypatch.setattr("worker.jobs.translate_definition.generate_with_schema", boom)
    monkeypatch.setattr(
        "worker.jobs.translate_definition.render", lambda *a, **k: "PROMPT"
    )

    def_id, job_id = await _seed_definition_and_job(
        session, job_type="translate_definition"
    )
    ctx = {"redis": fakeredis_client, "job_try": 2, "max_tries": 2}
    with pytest.raises(ValueError):
        await tr_mod.translate_definition(ctx, def_id, "fr", job_id)

    job_row = (
        await session.execute(
            text("SELECT status FROM jobs WHERE id = :id"), {"id": job_id}
        )
    ).one()
    assert job_row.status == "failed"


# --------------------------------------------------------------------------
# tts_render
# --------------------------------------------------------------------------


@pytest.fixture
def tts_env(monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")


async def test_tts_not_configured(session, arq_ctx, monkeypatch) -> None:
    monkeypatch.delenv("S3_BUCKET", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def_id, job_id = await _seed_definition_and_job(session, job_type="tts_render")

    result = await tts_mod.tts_render(arq_ctx, def_id, "en", job_id)
    assert result["status"] == "failed"
    assert result["reason"] == "not_configured"

    job_row = (
        await session.execute(
            text("SELECT status, error FROM jobs WHERE id = :id"), {"id": job_id}
        )
    ).one()
    assert job_row.status == "failed"
    assert job_row.error == "tts_not_configured"


async def test_tts_terminal_returns_duplicate(
    session, arq_ctx, tts_env
) -> None:
    """is_terminal gate short-circuits before the config check."""
    def_id, job_id = await _seed_definition_and_job(session, job_type="tts_render")
    await session.execute(
        text("UPDATE jobs SET status = 'completed' WHERE id = :id"), {"id": job_id}
    )
    await session.commit()

    result = await tts_mod.tts_render(arq_ctx, def_id, "en", job_id)
    assert result == {"status": "duplicate"}


async def test_tts_definition_not_found(session, arq_ctx, tts_env) -> None:
    job_id = str(uuid4())
    await session.execute(
        text(
            "INSERT INTO jobs (id, type, status, payload) "
            "VALUES (:id, 'tts_render', 'pending', '{}'::jsonb)"
        ),
        {"id": job_id},
    )
    await session.commit()

    result = await tts_mod.tts_render(arq_ctx, 999_999, "en", job_id)
    assert result["status"] == "failed"

    job_row = (
        await session.execute(
            text("SELECT status, error FROM jobs WHERE id = :id"), {"id": job_id}
        )
    ).one()
    assert job_row.status == "failed"
    assert job_row.error == "definition_not_found"


async def test_tts_happy_persists_url(
    session, arq_ctx, tts_env, monkeypatch
) -> None:
    async def fake_synth(script, lang):
        return b"\x00\x01mp3bytes"

    async def fake_upload(definition_id, lang, audio):
        return f"https://cdn.example/tts/{definition_id}/{lang}.mp3"

    monkeypatch.setattr("worker.jobs.tts_render.synthesize", fake_synth)
    monkeypatch.setattr("worker.jobs.tts_render._upload_and_sign", fake_upload)

    def_id, job_id = await _seed_definition_and_job(session, job_type="tts_render")

    result = await tts_mod.tts_render(arq_ctx, def_id, "en", job_id)
    assert result["status"] == "completed"

    row = (
        await session.execute(
            text("SELECT tts_url FROM definitions WHERE id = :id"), {"id": def_id}
        )
    ).one()
    tts_url = row.tts_url if isinstance(row.tts_url, dict) else json.loads(row.tts_url)
    assert tts_url["en"].endswith(f"/tts/{def_id}/en.mp3")

    job_row = (
        await session.execute(
            text("SELECT status FROM jobs WHERE id = :id"), {"id": job_id}
        )
    ).one()
    assert job_row.status == "completed"


async def test_tts_synth_failure_last_attempt_marks_failed(
    session, fakeredis_client, tts_env, monkeypatch
) -> None:
    """synthesize raises RuntimeError on final attempt → terminal `failed`."""
    async def boom(script, lang):
        raise RuntimeError("tts-engine-down")

    monkeypatch.setattr("worker.jobs.tts_render.synthesize", boom)

    def_id, job_id = await _seed_definition_and_job(session, job_type="tts_render")
    ctx = {"redis": fakeredis_client, "job_try": 2, "max_tries": 2}
    with pytest.raises(RuntimeError):
        await tts_mod.tts_render(ctx, def_id, "en", job_id)

    job_row = (
        await session.execute(
            text("SELECT status, error FROM jobs WHERE id = :id"), {"id": job_id}
        )
    ).one()
    assert job_row.status == "failed"


async def test_tts_upload_failure_last_attempt_marks_failed(
    session, fakeredis_client, tts_env, monkeypatch
) -> None:
    """upload raises on final attempt → terminal `failed` with upload_failed."""
    async def fake_synth(script, lang):
        return b"\x00mp3"

    async def boom_upload(definition_id, lang, audio):
        raise RuntimeError("b2-down")

    monkeypatch.setattr("worker.jobs.tts_render.synthesize", fake_synth)
    monkeypatch.setattr("worker.jobs.tts_render._upload_and_sign", boom_upload)

    def_id, job_id = await _seed_definition_and_job(session, job_type="tts_render")
    ctx = {"redis": fakeredis_client, "job_try": 2, "max_tries": 2}
    with pytest.raises(RuntimeError):
        await tts_mod.tts_render(ctx, def_id, "en", job_id)

    job_row = (
        await session.execute(
            text("SELECT status, error FROM jobs WHERE id = :id"), {"id": job_id}
        )
    ).one()
    assert job_row.status == "failed"
    assert job_row.error == "upload_failed"
