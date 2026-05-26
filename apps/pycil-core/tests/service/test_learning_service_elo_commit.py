"""ELO commit on session-completion threshold.

When `correct_firsts == _REQUIRED_CORRECT_FIRSTS (2)` the term is marked
complete and `_persist_review` writes `user_term_stats` (mastery_score,
NRD, interval, mastery_level).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import text

from pycil_core.services import learning_service as ls
from tests.factories import (
    attach_definition_to_deck,
    make_deck,
    make_definition,
    make_mcq_question,
    make_session_state,
    make_term,
)


async def test_elo_writes_at_required_correct_firsts(
    session, fakeredis_client, test_user
) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    term_id = await make_term(session, value="elo-commit-term")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=def_id)
    mcq = await make_mcq_question(
        session, definition_id=def_id, options=["X", "Y"], correct_index=0
    )

    sid = str(uuid4())
    # Pre-seed correct_firsts=1 — one correct answer takes us to threshold.
    state = make_session_state(
        session_id=sid,
        user_id=test_user["id"],
        deck_id=deck["id"],
        definition_ids=[def_id],
        correct_firsts={def_id: 1},
        current_question_id=str(mcq["id"]),
        current_definition_id=def_id,
    )
    await ls._save_state(fakeredis_client, sid, state)

    response = await ls.submit_answer(
        session,
        user_id=UUID(str(test_user["id"])),
        session_id=sid,
        question_id=UUID(str(mcq["id"])),
        selected_index=0,
    )

    assert response.correct is True
    assert response.term_reviewed is not None
    assert response.term_reviewed.definition_id == def_id
    assert response.session_complete is True

    # `user_term_stats` row was UPSERTed.
    row = (
        await session.execute(
            text(
                "SELECT mastery_score, mastery_level, interval_seconds, "
                "next_review_date "
                "FROM user_term_stats WHERE user_id = :u AND definition_id = :d"
            ),
            {"u": test_user["id"], "d": def_id},
        )
    ).first()
    assert row is not None
    assert row.mastery_score >= 1000  # gained from correct answer
    assert row.mastery_level >= 4
    assert row.interval_seconds >= 1800
    assert row.next_review_date > datetime.now(tz=timezone.utc)


async def test_wrong_answer_does_not_commit(
    session, fakeredis_client, test_user
) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    term_id = await make_term(session, value="elo-no-commit-term")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=def_id)
    mcq = await make_mcq_question(
        session, definition_id=def_id, options=["X", "Y"], correct_index=0
    )

    sid = str(uuid4())
    state = make_session_state(
        session_id=sid,
        user_id=test_user["id"],
        deck_id=deck["id"],
        definition_ids=[def_id],
        current_question_id=str(mcq["id"]),
        current_definition_id=def_id,
    )
    await ls._save_state(fakeredis_client, sid, state)

    # Wrong index.
    response = await ls.submit_answer(
        session,
        user_id=UUID(str(test_user["id"])),
        session_id=sid,
        question_id=UUID(str(mcq["id"])),
        selected_index=1,
    )
    assert response.correct is False
    assert response.term_reviewed is None

    # No `user_term_stats` row on a wrong first attempt.
    row = (
        await session.execute(
            text(
                "SELECT 1 FROM user_term_stats WHERE user_id = :u AND definition_id = :d"
            ),
            {"u": test_user["id"], "d": def_id},
        )
    ).first()
    assert row is None
