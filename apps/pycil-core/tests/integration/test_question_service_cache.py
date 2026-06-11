"""`question_service.get_or_generate` cache + answer-stripping.

Pinned:
- MCQ already in DB → response status="ready", answer fields stripped.
- WRITE-only pre-seed → not treated as cache → enqueue path.
- 404 oracle for unowned + private definitions (no 403 leak).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from pycil_core.services import question_service
from tests.factories import (
    attach_definition_to_deck,
    make_deck,
    make_definition,
    make_mcq_question,
    make_term,
    make_write_question,
)

_ANSWER_FIELDS = {
    "correct_index", "explanation", "distractor_rationale",
    "expected_answer", "alt_answers",
}


@pytest.fixture(autouse=True)
def _stub_arq_enqueue(monkeypatch):
    calls: list[dict] = []

    async def fake(job_name, *args, _job_id):
        calls.append({"name": job_name, "args": args, "job_id": _job_id})

    monkeypatch.setattr(
        "pycil_core.services.question_service.enqueue_arq_job", fake
    )
    return calls


async def test_cache_hit_returns_ready_with_stripped_data(
    session, test_user
) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    term_id = await make_term(session, value="cache-hit-term")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=def_id)
    await make_mcq_question(session, definition_id=def_id, correct_index=2)

    response = await question_service.get_or_generate(
        session, def_id, "easy", test_user["id"]
    )

    assert response.status == "ready"
    assert response.question is not None
    data = response.question.data
    assert isinstance(data, dict)
    assert _ANSWER_FIELDS.isdisjoint(data.keys())
    assert "stem" in data
    assert "options" in data


async def test_write_pre_seed_does_not_satisfy_mcq_cache(
    session, test_user, _stub_arq_enqueue
) -> None:
    """Cache lookup filters by `type='MULTIPLE_CHOICE'` — WRITE row should NOT
    short-circuit MCQ generation."""
    deck = await make_deck(session, author_id=test_user["id"])
    term_id = await make_term(session, value="write-only-term")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=def_id)
    await make_write_question(session, definition_id=def_id)

    response = await question_service.get_or_generate(
        session, def_id, "easy", test_user["id"]
    )

    # Pending → enqueue actually fired (the user owns lock or gets dedup).
    assert response.status == "pending"
    assert len(_stub_arq_enqueue) >= 1


async def test_unowned_private_definition_returns_404_oracle(
    session, test_user, second_user
) -> None:
    """Private deck owned by another user → 404, NOT 403 (no existence oracle)."""
    deck = await make_deck(
        session, author_id=second_user["id"], visibility="PRIVATE"
    )
    term_id = await make_term(session, value="private-other")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(
        session, deck_id=deck["id"], definition_id=def_id
    )

    with pytest.raises(HTTPException) as exc:
        await question_service.get_or_generate(
            session, def_id, "easy", test_user["id"]
        )
    assert exc.value.status_code == 404


async def test_other_user_public_deck_succeeds(
    session, test_user, second_user
) -> None:
    deck = await make_deck(
        session, author_id=second_user["id"], visibility="PUBLIC"
    )
    term_id = await make_term(session, value="public-other")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(
        session, deck_id=deck["id"], definition_id=def_id
    )
    await make_mcq_question(session, definition_id=def_id)

    response = await question_service.get_or_generate(
        session, def_id, "easy", test_user["id"]
    )
    assert response.status == "ready"


def test_strip_answer_fields_drops_protected_keys() -> None:
    raw = {
        "stem": "Q?",
        "options": ["a", "b"],
        "correct_index": 1,
        "explanation": "because",
        "distractor_rationale": ["r1"],
        "expected_answer": "x",
        "alt_answers": ["y"],
    }
    stripped = question_service._strip_answer_fields(raw)
    assert _ANSWER_FIELDS.isdisjoint(stripped.keys())
    assert "stem" in stripped
    assert "options" in stripped
