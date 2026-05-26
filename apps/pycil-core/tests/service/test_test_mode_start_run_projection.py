"""`test_mode_service.start_run` answer-stripped projection.

Pinned: payload returned to client must NOT contain `correct_index`,
`explanation`, `distractor_rationale` (MCQ) or `expected_answer`,
`alt_answers` (WRITE/FILL). View-source attack reveals nothing useful.
"""
from __future__ import annotations

from uuid import UUID

import pytest

from pycil_core.services import test_mode_service
from tests.factories import (
    attach_definition_to_deck,
    make_deck,
    make_definition,
    make_mcq_question,
    make_term,
    make_write_question,
)


_LEAK_KEYS_MCQ = {"correct_index", "explanation", "distractor_rationale"}
_LEAK_KEYS_WRITE = {"expected_answer", "alt_answers", "explanation"}


async def _seed_deck_with_mcqs(session, user_id, n: int = 3) -> tuple[UUID, list[int]]:
    deck = await make_deck(session, author_id=user_id)
    def_ids = []
    for i in range(n):
        tid = await make_term(session, value=f"mcq-leak-{i}")
        did = await make_definition(session, term_id=tid)
        await attach_definition_to_deck(
            session, deck_id=deck["id"], definition_id=did
        )
        await make_mcq_question(
            session, definition_id=did, correct_index=i % 4
        )
        def_ids.append(did)
    return deck["id"], def_ids


async def test_mcq_payload_strips_correct_index_and_explanation(
    session, test_user
) -> None:
    deck_id, _ = await _seed_deck_with_mcqs(session, test_user["id"], n=3)

    result = await test_mode_service.start_run(
        session,
        user_id=test_user["id"],
        deck_id=deck_id,
        question_count=3,
        types=["MULTIPLE_CHOICE"],
    )
    assert "items" in result
    for item in result["items"]:
        assert item["type"] == "MULTIPLE_CHOICE"
        assert _LEAK_KEYS_MCQ.isdisjoint(item.keys())
        assert "stem" in item
        assert "options" in item


async def test_write_payload_strips_expected_answer(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    tid = await make_term(session, value="write-leak")
    did = await make_definition(session, term_id=tid)
    await attach_definition_to_deck(
        session, deck_id=deck["id"], definition_id=did
    )
    await make_write_question(
        session,
        definition_id=did,
        prompt="Translate it.",
        expected_answer="leaked-answer",
        alt_answers=["leaked-alt"],
    )

    result = await test_mode_service.start_run(
        session,
        user_id=test_user["id"],
        deck_id=deck["id"],
        question_count=1,
        types=["WRITE"],
    )
    item = result["items"][0]
    assert item["type"] == "WRITE"
    assert _LEAK_KEYS_WRITE.isdisjoint(item.keys())
    assert "prompt" in item


async def test_empty_deck_raises(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])

    with pytest.raises(LookupError, match="no_questions_available"):
        await test_mode_service.start_run(
            session,
            user_id=test_user["id"],
            deck_id=deck["id"],
            question_count=5,
            types=["MULTIPLE_CHOICE"],
        )


async def test_private_deck_other_user_lookup_error(
    session, test_user, second_user
) -> None:
    deck = await make_deck(
        session, author_id=second_user["id"], visibility="PRIVATE"
    )

    with pytest.raises(LookupError, match="deck_not_found_or_not_accessible"):
        await test_mode_service.start_run(
            session,
            user_id=test_user["id"],
            deck_id=deck["id"],
            question_count=1,
            types=["MULTIPLE_CHOICE"],
        )


async def test_public_deck_other_user_succeeds(
    session, test_user, second_user
) -> None:
    deck_id, _ = await _seed_deck_with_mcqs(session, second_user["id"], n=2)
    # Make public.
    from sqlalchemy import text
    await session.execute(
        text("UPDATE nodes SET visibility = 'PUBLIC' WHERE id = :id"),
        {"id": deck_id},
    )
    await session.commit()

    result = await test_mode_service.start_run(
        session,
        user_id=test_user["id"],
        deck_id=deck_id,
        question_count=2,
        types=["MULTIPLE_CHOICE"],
    )
    assert len(result["items"]) == 2


async def test_partial_question_count_when_deck_smaller(
    session, test_user
) -> None:
    """Deck has 2 questions, requested 10 → returns 2."""
    deck_id, _ = await _seed_deck_with_mcqs(session, test_user["id"], n=2)

    result = await test_mode_service.start_run(
        session,
        user_id=test_user["id"],
        deck_id=deck_id,
        question_count=10,
        types=["MULTIPLE_CHOICE"],
    )
    assert len(result["items"]) == 2
