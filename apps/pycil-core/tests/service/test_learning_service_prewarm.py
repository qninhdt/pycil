"""Phase 3 session integration: prewarm-on-start + generic submit response.

Pinned:
- start_session fires question_bank_service.enqueue_prewarm for selected terms.
- A prewarm enqueue failure does NOT break session start (best-effort).
- SubmitAnswerResponse carries generic reveal/score plus back-compat fields.
"""
from __future__ import annotations

from pycil_core.schemas.learning import SubmitAnswerResponse
from pycil_core.services import learning_service as ls
from tests.factories import (
    attach_definition_to_deck,
    make_deck,
    make_definition,
    make_mcq_question,
    make_term,
)


async def test_start_session_enqueues_prewarm(session, test_user, monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_prewarm(definition_ids, user_id, *args, **kwargs):
        calls.append({"definition_ids": list(definition_ids), "user_id": user_id})

    monkeypatch.setattr(
        "pycil_core.services.question_bank_service.enqueue_prewarm", fake_prewarm
    )

    deck = await make_deck(session, author_id=test_user["id"])
    tid = await make_term(session, value="prewarm-on-start")
    did = await make_definition(session, term_id=tid)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=did)
    await make_mcq_question(session, definition_id=did)

    await ls.start_session(session, test_user["id"], deck["id"], session_size=1)

    assert len(calls) == 1
    assert did in calls[0]["definition_ids"]
    assert calls[0]["user_id"] == test_user["id"]


async def test_start_session_survives_prewarm_failure(
    session, test_user, monkeypatch
) -> None:
    async def boom(*args, **kwargs):
        raise RuntimeError("arq pool down")

    monkeypatch.setattr(
        "pycil_core.services.question_bank_service.enqueue_prewarm", boom
    )

    deck = await make_deck(session, author_id=test_user["id"])
    tid = await make_term(session, value="prewarm-failure-safe")
    did = await make_definition(session, term_id=tid)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=did)
    await make_mcq_question(session, definition_id=did)

    # Must not raise — prewarm is best-effort.
    resp = await ls.start_session(session, test_user["id"], deck["id"], session_size=1)
    assert resp.selected_count == 1


def test_submit_response_carries_generic_and_backcompat_fields() -> None:
    resp = SubmitAnswerResponse(
        correct=True,
        score=1.0,
        feedback="because",
        reveal={"correct_index": 2},
        explanation="because",
        correct_index=2,
    )
    assert resp.score == 1.0
    assert resp.reveal["correct_index"] == 2
    # Back-compat fields still present for the current MCQ FE.
    assert resp.correct_index == 2
    assert resp.explanation == "because"
