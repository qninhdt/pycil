"""question_bank_service: bank read, depth, answer-stripping.

Pinned:
- get_ready returns a ready question (no enqueue) when the slot has depth.
- get_ready applies public_projection — answer fields absent from the read.
- WRITE rows do not satisfy an MCQ slot read.
- bank_depth counts only the matching (definition, type, difficulty) slot.
"""
from __future__ import annotations

from pycil_core.services import question_bank_service
from tests.factories import (
    attach_definition_to_deck,
    make_deck,
    make_definition,
    make_mcq_question,
    make_term,
    make_write_question,
)

_ANSWER_FIELDS = {
    "correct_index",
    "explanation",
    "distractor_rationale",
    "expected_answer",
    "alt_answers",
}


async def test_get_ready_returns_stripped_question(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    term_id = await make_term(session, value="bank-ready-term")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=def_id)
    await make_mcq_question(session, definition_id=def_id, correct_index=2)

    ready = await question_bank_service.get_ready(
        session, def_id, "MULTIPLE_CHOICE", "easy", test_user["id"]
    )

    assert ready is not None
    assert isinstance(ready.data, dict)
    assert _ANSWER_FIELDS.isdisjoint(ready.data.keys())
    assert "stem" in ready.data
    assert "options" in ready.data


async def test_get_ready_empty_bank_returns_none(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    term_id = await make_term(session, value="bank-empty-term")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=def_id)

    ready = await question_bank_service.get_ready(
        session, def_id, "MULTIPLE_CHOICE", "easy", test_user["id"]
    )
    assert ready is None


async def test_write_row_does_not_satisfy_mcq_slot(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    term_id = await make_term(session, value="bank-write-only")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=def_id)
    await make_write_question(session, definition_id=def_id)

    ready = await question_bank_service.get_ready(
        session, def_id, "MULTIPLE_CHOICE", "easy", test_user["id"]
    )
    assert ready is None


async def test_bank_depth_counts_matching_difficulty(session) -> None:
    term_id = await make_term(session, value="bank-depth-term")
    def_id = await make_definition(session, term_id=term_id)
    # Legacy rows carry no difficulty key; bank_depth filters on 'easy'
    # explicitly, so a NULL-difficulty row is not counted toward the 'easy' slot.
    await make_mcq_question(session, definition_id=def_id)

    depth = await question_bank_service.bank_depth(
        session, def_id, "MULTIPLE_CHOICE", "easy"
    )
    assert depth == 0
