"""`test_mode_service.submit_answer` + `complete_run` aggregation.

Pinned:
- MCQ correct → `is_correct=True`, `reason="exact"`.
- MCQ malformed user_answer (non-int string) → `is_correct=False`, no crash.
- WRITE dispatches to `answer_grading_service.grade()`.
- Replay submit → `ValueError("already_answered")`.
- Submit after `complete_run` → `ValueError("run_completed")`.
- Cross-user submit → `LookupError("item_not_found")`.
- `complete_run`: empty run → `score_pct == 0.0` (no DivByZero).
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


async def _start_mcq_run(session, user_id, *, correct_index: int = 2):
    deck = await make_deck(session, author_id=user_id)
    tid = await make_term(session, value=f"submit-mcq-{user_id}")
    did = await make_definition(session, term_id=tid)
    await attach_definition_to_deck(
        session, deck_id=deck["id"], definition_id=did
    )
    await make_mcq_question(
        session, definition_id=did, correct_index=correct_index
    )

    run = await test_mode_service.start_run(
        session, user_id=user_id, deck_id=deck["id"],
        question_count=1, types=["MULTIPLE_CHOICE"],
    )
    return UUID(run["run_id"]), UUID(run["items"][0]["item_id"])


async def test_mcq_correct_answer(session, test_user) -> None:
    rid, iid = await _start_mcq_run(session, test_user["id"], correct_index=2)
    result = await test_mode_service.submit_answer(
        session,
        user_id=test_user["id"],
        run_id=rid,
        item_id=iid,
        user_answer="2",
    )
    assert result == {"is_correct": True, "reason": "exact"}


async def test_mcq_malformed_user_answer_returns_incorrect(
    session, test_user
) -> None:
    rid, iid = await _start_mcq_run(session, test_user["id"], correct_index=0)
    result = await test_mode_service.submit_answer(
        session,
        user_id=test_user["id"],
        run_id=rid,
        item_id=iid,
        user_answer="not-an-int",
    )
    assert result["is_correct"] is False
    # No exception.


async def test_write_dispatches_to_grader(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    tid = await make_term(session, value="write-submit")
    did = await make_definition(session, term_id=tid)
    await attach_definition_to_deck(
        session, deck_id=deck["id"], definition_id=did
    )
    await make_write_question(
        session, definition_id=did,
        prompt="Translate it.", expected_answer="hello", alt_answers=[],
    )

    run = await test_mode_service.start_run(
        session, user_id=test_user["id"], deck_id=deck["id"],
        question_count=1, types=["WRITE"],
    )
    rid = UUID(run["run_id"])
    iid = UUID(run["items"][0]["item_id"])

    result = await test_mode_service.submit_answer(
        session, user_id=test_user["id"], run_id=rid, item_id=iid,
        user_answer="hello",
    )
    assert result["is_correct"] is True
    assert result["reason"] in ("exact", "normalized", "fuzzy", "no_match")


async def test_replay_submit_raises_already_answered(session, test_user) -> None:
    rid, iid = await _start_mcq_run(session, test_user["id"], correct_index=0)
    await test_mode_service.submit_answer(
        session, user_id=test_user["id"], run_id=rid, item_id=iid,
        user_answer="0",
    )
    with pytest.raises(ValueError, match="already_answered"):
        await test_mode_service.submit_answer(
            session, user_id=test_user["id"], run_id=rid, item_id=iid,
            user_answer="1",
        )


async def test_submit_after_complete_raises(session, test_user) -> None:
    rid, iid = await _start_mcq_run(session, test_user["id"], correct_index=0)
    await test_mode_service.complete_run(
        session, user_id=test_user["id"], run_id=rid
    )
    with pytest.raises(ValueError, match="run_completed"):
        await test_mode_service.submit_answer(
            session, user_id=test_user["id"], run_id=rid, item_id=iid,
            user_answer="0",
        )


async def test_cross_user_submit_lookup_error(
    session, test_user, second_user
) -> None:
    rid, iid = await _start_mcq_run(session, test_user["id"], correct_index=0)
    with pytest.raises(LookupError, match="item_not_found"):
        await test_mode_service.submit_answer(
            session, user_id=second_user["id"], run_id=rid, item_id=iid,
            user_answer="0",
        )


async def test_empty_run_zero_score_no_div_by_zero(session, test_user) -> None:
    """A run with zero items should aggregate to score_pct=0.0 cleanly."""
    from sqlalchemy import text

    deck = await make_deck(session, author_id=test_user["id"])
    # Manually INSERT a run with 0 items (start_run rejects empty decks).
    rid_row = (
        await session.execute(
            text(
                "INSERT INTO test_runs (user_id, deck_id, question_count) "
                "VALUES (:u, :d, 0) RETURNING id"
            ),
            {"u": test_user["id"], "d": deck["id"]},
        )
    ).one()
    await session.commit()

    summary = await test_mode_service.complete_run(
        session, user_id=test_user["id"], run_id=rid_row.id
    )
    assert summary["total"] == 0
    assert summary["score_pct"] == 0.0


async def test_complete_run_score_aggregation(session, test_user) -> None:
    """3 items, 2 correct → score_pct == 200/3."""
    deck = await make_deck(session, author_id=test_user["id"])
    items_iids = []
    for i in range(3):
        tid = await make_term(session, value=f"agg-{i}")
        did = await make_definition(session, term_id=tid)
        await attach_definition_to_deck(
            session, deck_id=deck["id"], definition_id=did
        )
        await make_mcq_question(
            session, definition_id=did, correct_index=0
        )

    run = await test_mode_service.start_run(
        session, user_id=test_user["id"], deck_id=deck["id"],
        question_count=3, types=["MULTIPLE_CHOICE"],
    )
    rid = UUID(run["run_id"])
    items_iids = [UUID(item["item_id"]) for item in run["items"]]

    # 2 correct, 1 wrong.
    await test_mode_service.submit_answer(
        session, user_id=test_user["id"], run_id=rid, item_id=items_iids[0],
        user_answer="0",
    )
    await test_mode_service.submit_answer(
        session, user_id=test_user["id"], run_id=rid, item_id=items_iids[1],
        user_answer="0",
    )
    await test_mode_service.submit_answer(
        session, user_id=test_user["id"], run_id=rid, item_id=items_iids[2],
        user_answer="1",
    )

    summary = await test_mode_service.complete_run(
        session, user_id=test_user["id"], run_id=rid
    )
    assert summary["correct_count"] == 2
    assert summary["total"] == 3
    assert summary["score_pct"] == pytest.approx(200.0 / 3)
