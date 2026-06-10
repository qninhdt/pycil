"""Coverage for `question_service`: get_or_generate generation path,
check_answer dispatch (sync/async), access-control oracles, and helpers.

Complements test_question_service_cache.py (cache-hit + answer stripping) by
exercising the cold-start enqueue path, the enqueue-failure rollback, the
plugin-registry check_answer dispatch, and the question-access 404 oracle.
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from pycil_core.schemas.grading import AsyncGradePending
from pycil_core.schemas.question import QuestionCheckResponse
from pycil_core.services import question_service
from tests.factories import (
    attach_definition_to_deck,
    make_deck,
    make_definition,
    make_mcq_question,
    make_term,
)


@pytest.fixture
def _stub_arq_enqueue(monkeypatch):
    """Capture generate_question enqueue calls (no real arq pool in tests)."""
    calls: list[dict] = []

    async def fake(job_name, *args, _job_id):
        calls.append({"name": job_name, "args": args, "job_id": _job_id})

    monkeypatch.setattr(
        "pycil_core.services.question_service.enqueue_arq_job", fake
    )
    return calls


async def _insert_fill_question(session, *, definition_id: int) -> str:
    data = {
        "prompt": "The cat sat on the ___.",
        "expected_answer": "mat",
        "alt_answers": ["rug"],
        "explanation": "rhymes with cat",
    }
    row = (
        await session.execute(
            text(
                """
                INSERT INTO questions (definition_id, type, data)
                VALUES (:did, CAST('FILL_IN_BLANK' AS question_type),
                        CAST(:data AS jsonb))
                RETURNING id
                """
            ),
            {"did": definition_id, "data": json.dumps(data)},
        )
    ).one()
    await session.commit()
    return row.id


# ---------------------------------------------------------------------------
# get_or_generate: difficulty normalization + cold-start enqueue.
# ---------------------------------------------------------------------------

async def test_invalid_difficulty_normalizes_to_easy_and_serves_bank(
    session, test_user
) -> None:
    """Unknown difficulty coerces to 'easy'; a seeded MCQ still serves ready."""
    deck = await make_deck(session, author_id=test_user["id"])
    term_id = await make_term(session, value="diff-normalize-term")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=def_id)
    await make_mcq_question(session, definition_id=def_id)

    resp = await question_service.get_or_generate(
        session, def_id, "nonsense-difficulty", test_user["id"]
    )
    assert resp.status == "ready"
    assert resp.question is not None


async def test_cold_start_enqueues_generation_and_writes_pending_job(
    session, test_user, _stub_arq_enqueue
) -> None:
    """No bank depth → lock owner inserts a pending job row + enqueues arq."""
    deck = await make_deck(session, author_id=test_user["id"])
    term_id = await make_term(session, value="cold-start-term")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=def_id)

    resp = await question_service.get_or_generate(
        session, def_id, "easy", test_user["id"]
    )
    assert resp.status == "pending"
    assert len(_stub_arq_enqueue) == 1

    job = (
        await session.execute(
            text(
                "SELECT type, status, payload FROM jobs "
                "WHERE id = :id"
            ),
            {"id": _stub_arq_enqueue[0]["job_id"]},
        )
    ).first()
    assert job is not None
    assert job.type == "generate_question"
    assert job.status == "pending"
    payload = job.payload if isinstance(job.payload, dict) else json.loads(job.payload)
    assert payload["definition_id"] == def_id
    assert payload["type"] == "MULTIPLE_CHOICE"


async def test_enqueue_failure_marks_job_failed_and_releases_lock(
    session, test_user, monkeypatch, fakeredis_client
) -> None:
    """If arq enqueue raises, the job row is marked failed, the single-flight
    lock is released, and the error propagates."""
    captured: dict = {}

    async def boom(job_name, *args, _job_id):
        captured["job_id"] = _job_id
        raise RuntimeError("arq pool down")

    monkeypatch.setattr(
        "pycil_core.services.question_service.enqueue_arq_job", boom
    )

    deck = await make_deck(session, author_id=test_user["id"])
    term_id = await make_term(session, value="enqueue-fail-term")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=def_id)

    with pytest.raises(RuntimeError):
        await question_service.get_or_generate(
            session, def_id, "easy", test_user["id"]
        )

    # Job row flipped to failed.
    job = (
        await session.execute(
            text("SELECT status, error FROM jobs WHERE id = :id"),
            {"id": captured["job_id"]},
        )
    ).first()
    assert job is not None
    assert job.status == "failed"
    assert job.error == "enqueue_failed"

    # Lock released so a retry can re-acquire ownership.
    lock_key = f"lock:gen_question:{def_id}:MULTIPLE_CHOICE"
    assert await fakeredis_client.get(lock_key) is None


# ---------------------------------------------------------------------------
# _existing_question + _strip_answer_fields helpers.
# ---------------------------------------------------------------------------

async def test_existing_question_returns_stripped_read(session, test_user) -> None:
    term_id = await make_term(session, value="existing-q-term")
    def_id = await make_definition(session, term_id=term_id)
    await make_mcq_question(session, definition_id=def_id, correct_index=1)

    read = await question_service._existing_question(session, def_id)
    assert read is not None
    assert read.definition_id == def_id
    assert read.type == "MULTIPLE_CHOICE"
    assert isinstance(read.data, dict)
    assert "correct_index" not in read.data
    assert "stem" in read.data


async def test_existing_question_none_when_no_mcq(session) -> None:
    term_id = await make_term(session, value="no-mcq-term")
    def_id = await make_definition(session, term_id=term_id)
    assert await question_service._existing_question(session, def_id) is None


def test_strip_answer_fields_passthrough_non_dict() -> None:
    # Non-dict input is returned unchanged (defensive guard).
    assert question_service._strip_answer_fields("not-a-dict") == "not-a-dict"


# ---------------------------------------------------------------------------
# check_answer: access oracle + plugin dispatch.
# ---------------------------------------------------------------------------

async def test_check_answer_unowned_private_question_404_oracle(
    session, test_user, second_user
) -> None:
    """A question reachable only through another user's PRIVATE deck → 404."""
    deck = await make_deck(
        session, author_id=second_user["id"], visibility="PRIVATE"
    )
    term_id = await make_term(session, value="check-private-term")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=def_id)
    q = await make_mcq_question(session, definition_id=def_id)

    with pytest.raises(HTTPException) as exc:
        await question_service.check_answer(
            session, q["id"], 0, test_user["id"]
        )
    assert exc.value.status_code == 404


async def test_check_answer_question_not_found(session, test_user) -> None:
    from uuid import uuid4

    # No access row at all for a random id → access oracle fires 404 first.
    with pytest.raises(HTTPException) as exc:
        await question_service.check_answer(
            session, uuid4(), 0, test_user["id"]
        )
    assert exc.value.status_code == 404


async def test_check_answer_mcq_correct_and_incorrect(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    term_id = await make_term(session, value="check-mcq-term")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=def_id)
    q = await make_mcq_question(session, definition_id=def_id, correct_index=2)

    right = await question_service.check_answer(session, q["id"], 2, test_user["id"])
    assert isinstance(right, QuestionCheckResponse)
    assert right.correct is True
    assert right.correct_index == 2

    wrong = await question_service.check_answer(session, q["id"], 0, test_user["id"])
    assert wrong.correct is False
    assert wrong.correct_index == 2


async def test_check_answer_fill_sync_correct_index_fallback(
    session, test_user
) -> None:
    """FILL is sync but its reveal carries no correct_index → fallback path
    resolves correct_index to 0."""
    deck = await make_deck(session, author_id=test_user["id"])
    term_id = await make_term(session, value="check-fill-term")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=def_id)
    qid = await _insert_fill_question(session, definition_id=def_id)

    resp = await question_service.check_answer(
        session, qid, 0, test_user["id"], answer={"user_answer": "mat"}
    )
    assert isinstance(resp, QuestionCheckResponse)
    assert resp.correct is True
    assert resp.correct_index == 0


async def test_check_answer_async_write_returns_pending(
    session, test_user, monkeypatch
) -> None:
    """WRITE (requires_server_grading) enqueues an async grade and returns
    AsyncGradePending without an inline verdict."""
    async def fake_enqueue(job_name, *args, _job_id):
        return None

    monkeypatch.setattr(
        "pycil_core.services.async_grade_service.enqueue_arq_job", fake_enqueue
    )

    deck = await make_deck(session, author_id=test_user["id"])
    term_id = await make_term(session, value="check-write-term")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=def_id)
    data = {
        "prompt": "Define the term.",
        "expected_answer": "a thing",
        "alt_answers": [],
        "explanation": "",
    }
    row = (
        await session.execute(
            text(
                """
                INSERT INTO questions (definition_id, type, data)
                VALUES (:did, CAST('WRITE' AS question_type), CAST(:data AS jsonb))
                RETURNING id
                """
            ),
            {"did": def_id, "data": json.dumps(data)},
        )
    ).one()
    await session.commit()

    result = await question_service.check_answer(
        session, row.id, 0, test_user["id"], answer={"user_answer": "guess"}
    )
    assert isinstance(result, AsyncGradePending)
    assert result.grading == "pending"
