"""Coverage for `learning_service`: next_question round flow, async-verdict
application, submit_answer branch edges, start_session guards, and the
initial-ELO hydration / previous-review helpers.

Complements the existing learning_service test files (lock, authz, elo_commit,
round_queue, prewarm, concurrency, state) by driving the still-uncovered
next_question + apply_async_verdict orchestration and the start_session
validation branches.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from pycil_core.services.learning import (
    answer_grading,
    session_flow,
    session_state,
)
from tests.factories import (
    attach_definition_to_deck,
    make_deck,
    make_definition,
    make_mcq_question,
    make_session_state,
    make_term,
    seed_user_term_stats,
)


@pytest.fixture
def _stub_gen_enqueue(monkeypatch):
    """No real arq pool: stub the generate_question enqueue used by the
    cold-start path inside question_service.get_or_generate."""
    calls: list[dict] = []

    async def fake(job_name, *args, _job_id):
        calls.append({"name": job_name, "job_id": _job_id})

    monkeypatch.setattr(
        "pycil_core.services.question_service.enqueue_arq_job", fake
    )
    return calls


async def _seed_deck_def_mcq(session, user_id, *, term: str):
    deck = await make_deck(session, author_id=user_id)
    term_id = await make_term(session, value=term)
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=def_id)
    mcq = await make_mcq_question(session, definition_id=def_id, correct_index=0)
    return deck, def_id, mcq


# ---------------------------------------------------------------------------
# next_question
# ---------------------------------------------------------------------------

async def test_next_question_ready_serves_bank_and_sets_current(
    session, fakeredis_client, test_user
) -> None:
    deck, def_id, mcq = await _seed_deck_def_mcq(
        session, test_user["id"], term="nq-ready-term"
    )

    sid = str(uuid4())
    state = make_session_state(
        session_id=sid,
        user_id=test_user["id"],
        deck_id=deck["id"],
        definition_ids=[def_id],
    )
    await session_state._save_state(fakeredis_client, sid, state)

    resp = await session_flow.next_question(session, UUID(str(test_user["id"])), sid)
    assert resp.status == "ready"
    assert resp.question is not None
    assert resp.question["definition_id"] == def_id
    assert resp.theme is not None  # themed-pool rotation (no session theme)

    # State now points at the served question.
    loaded = await session_state._load_state(fakeredis_client, sid)
    assert loaded["current_question_id"] == str(mcq["id"])
    assert loaded["current_definition_id"] == def_id


async def test_next_question_pending_when_generation_cold_start(
    session, fakeredis_client, test_user, _stub_gen_enqueue
) -> None:
    """No bank depth → get_or_generate returns pending → next_question reports
    pending without advancing current_question_id."""
    deck = await make_deck(session, author_id=test_user["id"])
    term_id = await make_term(session, value="nq-pending-term")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=def_id)

    sid = str(uuid4())
    state = make_session_state(
        session_id=sid,
        user_id=test_user["id"],
        deck_id=deck["id"],
        definition_ids=[def_id],
    )
    await session_state._save_state(fakeredis_client, sid, state)

    resp = await session_flow.next_question(session, UUID(str(test_user["id"])), sid)
    assert resp.status == "pending"
    assert len(_stub_gen_enqueue) >= 1

    loaded = await session_state._load_state(fakeredis_client, sid)
    assert loaded["current_question_id"] is None


async def test_next_question_session_complete_when_all_done(
    session, fakeredis_client, test_user
) -> None:
    sid = str(uuid4())
    state = make_session_state(
        session_id=sid,
        user_id=test_user["id"],
        deck_id=uuid4(),
        definition_ids=[1, 2],
        completed=[1, 2],
    )
    await session_state._save_state(fakeredis_client, sid, state)

    resp = await session_flow.next_question(session, UUID(str(test_user["id"])), sid)
    assert resp.status == "session_complete"


async def test_next_question_replenishes_empty_round_queue(
    session, fakeredis_client, test_user
) -> None:
    """round_queue empty but an incomplete term remains → a fresh round opens
    (round_index increments) and a question is served."""
    deck, def_id, mcq = await _seed_deck_def_mcq(
        session, test_user["id"], term="nq-replenish-term"
    )

    sid = str(uuid4())
    state = make_session_state(
        session_id=sid,
        user_id=test_user["id"],
        deck_id=deck["id"],
        definition_ids=[def_id],
        round_index=0,
    )
    # Force an empty round_queue with the term still incomplete.
    state["round_queue"] = []
    await session_state._save_state(fakeredis_client, sid, state)

    resp = await session_flow.next_question(session, UUID(str(test_user["id"])), sid)
    assert resp.status == "ready"
    assert resp.round_index == 1  # incremented on replenish


async def test_next_question_wrong_user_403(
    session, fakeredis_client, test_user, second_user
) -> None:
    sid = str(uuid4())
    state = make_session_state(
        session_id=sid,
        user_id=test_user["id"],
        deck_id=uuid4(),
        definition_ids=[1],
    )
    await session_state._save_state(fakeredis_client, sid, state)

    with pytest.raises(HTTPException) as exc:
        await session_flow.next_question(session, UUID(str(second_user["id"])), sid)
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# submit_answer: branch edges (question_not_found, async enqueue path).
# ---------------------------------------------------------------------------

async def test_submit_answer_question_not_found_404(
    session, fakeredis_client, test_user
) -> None:
    """current_question_id matches the request but the row doesn't exist."""
    ghost_qid = uuid4()
    sid = str(uuid4())
    state = make_session_state(
        session_id=sid,
        user_id=test_user["id"],
        deck_id=uuid4(),
        definition_ids=[1],
        current_question_id=str(ghost_qid),
        current_definition_id=1,
    )
    await session_state._save_state(fakeredis_client, sid, state)

    with pytest.raises(HTTPException) as exc:
        await answer_grading.submit_answer(
            session,
            user_id=UUID(str(test_user["id"])),
            session_id=sid,
            question_id=ghost_qid,
            selected_index=0,
        )
    assert exc.value.status_code == 404


async def test_submit_answer_async_write_returns_pending_no_state_mutation(
    session, fakeredis_client, test_user, monkeypatch
) -> None:
    """A WRITE answer enqueues async grading and returns AsyncGradePending; the
    session round_queue must NOT advance (apply happens later)."""
    from pycil_core.schemas.grading import AsyncGradePending

    async def fake_enqueue(job_name, *args, _job_id):
        return None

    monkeypatch.setattr(
        "pycil_core.services.async_grade_service.enqueue_arq_job", fake_enqueue
    )

    deck = await make_deck(session, author_id=test_user["id"])
    term_id = await make_term(session, value="submit-write-term")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=def_id)
    data = {
        "prompt": "Define it.",
        "expected_answer": "x",
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
            {"did": def_id, "data": __import__("json").dumps(data)},
        )
    ).one()
    await session.commit()

    sid = str(uuid4())
    state = make_session_state(
        session_id=sid,
        user_id=test_user["id"],
        deck_id=deck["id"],
        definition_ids=[def_id],
        current_question_id=str(row.id),
        current_definition_id=def_id,
    )
    await session_state._save_state(fakeredis_client, sid, state)

    result = await answer_grading.submit_answer(
        session,
        user_id=UUID(str(test_user["id"])),
        session_id=sid,
        question_id=UUID(str(row.id)),
        selected_index=0,
        answer={"user_answer": "guess"},
    )
    assert isinstance(result, AsyncGradePending)

    # Queue untouched — async path defers state mutation.
    loaded = await session_state._load_state(fakeredis_client, sid)
    assert loaded["round_queue"] == [def_id]


# ---------------------------------------------------------------------------
# _previous_review: existing-row lapsed branch (drives 369-370).
# ---------------------------------------------------------------------------

async def test_completion_uses_previous_review_when_stats_exist(
    session, fakeredis_client, test_user
) -> None:
    """A pre-existing user_term_stats row makes _previous_review return a real
    lapsed/interval pair, feeding the ELO time-factor on completion."""
    deck, def_id, mcq = await _seed_deck_def_mcq(
        session, test_user["id"], term="prev-review-term"
    )
    await seed_user_term_stats(
        session,
        user_id=test_user["id"],
        definition_id=def_id,
        mastery_score=1200,
        interval_seconds=1800,
        last_review_offset_seconds=3600,
    )

    lapsed, interval_old = await answer_grading._previous_review(
        session, test_user["id"], def_id
    )
    assert lapsed is not None and lapsed > 0
    assert interval_old == 1800.0

    sid = str(uuid4())
    state = make_session_state(
        session_id=sid,
        user_id=test_user["id"],
        deck_id=deck["id"],
        definition_ids=[def_id],
        correct_firsts={def_id: 1},  # one more correct → completes
        current_question_id=str(mcq["id"]),
        current_definition_id=def_id,
    )
    await session_state._save_state(fakeredis_client, sid, state)

    resp = await answer_grading.submit_answer(
        session,
        user_id=UUID(str(test_user["id"])),
        session_id=sid,
        question_id=UUID(str(mcq["id"])),
        selected_index=0,
    )
    assert resp.term_reviewed is not None


async def test_previous_review_missing_returns_none_zero(session, test_user) -> None:
    lapsed, interval_old = await answer_grading._previous_review(
        session, test_user["id"], 999_999
    )
    assert lapsed is None
    assert interval_old == 0.0


# ---------------------------------------------------------------------------
# apply_async_verdict
# ---------------------------------------------------------------------------

async def _insert_graded_response(
    session,
    *,
    user_id,
    question_id,
    session_id: str,
    is_correct: bool = True,
    score: float = 1.0,
    feedback: str = "good work",
):
    rid = uuid4()
    await session.execute(
        text(
            """
            INSERT INTO responses (
                id, user_id, question_id, is_correct, user_answer,
                grade_status, session_id, elo_applied, grade_score, grade_feedback
            )
            VALUES (
                :id, :uid, :qid, :correct, 'an answer',
                'graded', :sid, FALSE, :score, :feedback
            )
            """
        ),
        {
            "id": rid,
            "uid": user_id,
            "qid": question_id,
            "correct": is_correct,
            "sid": session_id,
            "score": score,
            "feedback": feedback,
        },
    )
    await session.commit()
    return rid


async def test_apply_async_verdict_applies_then_idempotent(
    session, fakeredis_client, test_user
) -> None:
    deck, def_id, mcq = await _seed_deck_def_mcq(
        session, test_user["id"], term="async-verdict-term"
    )

    sid = str(uuid4())
    state = make_session_state(
        session_id=sid,
        user_id=test_user["id"],
        deck_id=deck["id"],
        definition_ids=[def_id],
        correct_firsts={def_id: 1},  # this correct verdict completes the term
        current_definition_id=def_id,
    )
    await session_state._save_state(fakeredis_client, sid, state)

    rid = await _insert_graded_response(
        session,
        user_id=test_user["id"],
        question_id=mcq["id"],
        session_id=sid,
        is_correct=True,
        score=1.0,
    )

    resp = await answer_grading.apply_async_verdict(
        session, UUID(str(test_user["id"])), sid, UUID(str(rid))
    )
    assert resp.correct is True
    assert resp.score == 1.0
    assert resp.term_reviewed is not None

    # elo_applied flipped to TRUE.
    flag = (
        await session.execute(
            text("SELECT elo_applied FROM responses WHERE id = :id"),
            {"id": rid},
        )
    ).first()
    assert flag.elo_applied is True

    # Second call: idempotent no-op (no re-credit, term_reviewed None).
    resp2 = await answer_grading.apply_async_verdict(
        session, UUID(str(test_user["id"])), sid, UUID(str(rid))
    )
    assert resp2.correct is True
    assert resp2.term_reviewed is None
    assert resp2.round_complete is False
    assert resp2.session_complete is False


async def test_apply_async_verdict_response_not_found_404(
    session, fakeredis_client, test_user
) -> None:
    with pytest.raises(HTTPException) as exc:
        await answer_grading.apply_async_verdict(
            session, UUID(str(test_user["id"])), "sess-x", uuid4()
        )
    assert exc.value.status_code == 404


async def test_apply_async_verdict_wrong_user_403(
    session, fakeredis_client, test_user, second_user
) -> None:
    deck, def_id, mcq = await _seed_deck_def_mcq(
        session, test_user["id"], term="async-verdict-403-term"
    )
    sid = str(uuid4())
    rid = await _insert_graded_response(
        session,
        user_id=test_user["id"],
        question_id=mcq["id"],
        session_id=sid,
    )

    with pytest.raises(HTTPException) as exc:
        await answer_grading.apply_async_verdict(
            session, UUID(str(second_user["id"])), sid, UUID(str(rid))
        )
    assert exc.value.status_code == 403


async def test_apply_async_verdict_grade_pending_409(
    session, fakeredis_client, test_user
) -> None:
    deck, def_id, mcq = await _seed_deck_def_mcq(
        session, test_user["id"], term="async-verdict-409-term"
    )
    sid = str(uuid4())
    rid = uuid4()
    await session.execute(
        text(
            """
            INSERT INTO responses (
                id, user_id, question_id, is_correct,
                grade_status, session_id, elo_applied
            )
            VALUES (:id, :uid, :qid, FALSE, 'pending', :sid, FALSE)
            """
        ),
        {"id": rid, "uid": test_user["id"], "qid": mcq["id"], "sid": sid},
    )
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await answer_grading.apply_async_verdict(
            session, UUID(str(test_user["id"])), sid, UUID(str(rid))
        )
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# start_session validation guards + initial-ELO hydration.
# ---------------------------------------------------------------------------

async def test_start_session_unknown_theme_400(session, test_user) -> None:
    with pytest.raises(HTTPException) as exc:
        await session_flow.start_session(
            session, test_user["id"], uuid4(), session_size=1,
            theme_id="no-such-theme",
        )
    assert exc.value.status_code == 400


async def test_start_session_deck_not_found_404(session, test_user) -> None:
    with pytest.raises(HTTPException) as exc:
        await session_flow.start_session(session, test_user["id"], uuid4(), session_size=1)
    assert exc.value.status_code == 404


async def test_start_session_deck_forbidden_403(
    session, test_user, second_user
) -> None:
    deck = await make_deck(session, author_id=second_user["id"])
    with pytest.raises(HTTPException) as exc:
        await session_flow.start_session(session, test_user["id"], deck["id"], session_size=1)
    assert exc.value.status_code == 403


async def test_start_session_node_not_deck_400(session, test_user) -> None:
    # Insert a FOLDER node owned by the user — wrong node type for a session.
    row = (
        await session.execute(
            text(
                """
                INSERT INTO nodes (author_id, type, name, visibility)
                VALUES (:aid, 'FOLDER', 'A Folder', CAST('PRIVATE' AS visibility))
                RETURNING id
                """
            ),
            {"aid": test_user["id"]},
        )
    ).one()
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await session_flow.start_session(session, test_user["id"], row.id, session_size=1)
    assert exc.value.status_code == 400


async def test_start_session_no_terms_400(session, test_user) -> None:
    """A deck with no linked definitions yields an empty selection → 400."""
    deck = await make_deck(session, author_id=test_user["id"])
    with pytest.raises(HTTPException) as exc:
        await session_flow.start_session(session, test_user["id"], deck["id"], session_size=5)
    assert exc.value.status_code == 400


async def test_start_session_hydrates_initial_elo_from_stats(
    session, fakeredis_client, test_user, monkeypatch
) -> None:
    """Pre-existing user_term_stats overrides the 1000 default in state."""
    async def fake_prewarm(definition_ids, user_id, *args, **kwargs):
        return None

    monkeypatch.setattr(
        "pycil_core.services.question_bank_service.enqueue_prewarm", fake_prewarm
    )

    deck, def_id, _mcq = await _seed_deck_def_mcq(
        session, test_user["id"], term="hydrate-elo-term"
    )
    await seed_user_term_stats(
        session,
        user_id=test_user["id"],
        definition_id=def_id,
        mastery_score=1450,
        interval_seconds=1800,
        last_review_offset_seconds=3600,
    )

    resp = await session_flow.start_session(
        session, test_user["id"], deck["id"], session_size=5
    )
    assert resp.selected_count >= 1

    loaded = await session_state._load_state(fakeredis_client, resp.session_id)
    assert loaded["term_tracking"][str(def_id)]["elo_at_start"] == 1450
