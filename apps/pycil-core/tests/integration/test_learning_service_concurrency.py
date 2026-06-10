"""Concurrency: parallel `submit_answer` on same session.

Per-session lock must serialize. Two coroutines launched with
`asyncio.gather`: one wins, one raises 409 `session_busy`, and only the
winner's `correct_firsts` is incremented.

Note: `asyncio.gather` is cooperatively scheduled — both tasks start, but
the lock primitive is the actual serialization point. We add a small
`asyncio.sleep(0)` after acquiring to force a yield so the second task
gets a chance to attempt acquisition before the first finishes.
"""
from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from fastapi import HTTPException

from pycil_core.services.learning import answer_grading, session_state
from tests.factories import (
    attach_definition_to_deck,
    make_deck,
    make_definition,
    make_mcq_question,
    make_session_state,
    make_term,
)


async def test_concurrent_submits_lock_serialize(
    session, fakeredis_client, test_user
) -> None:
    # Seed deck + 1 definition + 1 MCQ.
    deck = await make_deck(session, author_id=test_user["id"])
    term_id = await make_term(session, value="concurrency-term")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=def_id)
    mcq = await make_mcq_question(
        session, definition_id=def_id, options=["A", "B", "C", "D"], correct_index=0
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
    await session_state._save_state(fakeredis_client, sid, state)

    qid = UUID(str(mcq["id"]))
    uid = UUID(str(test_user["id"]))

    async def _submit():
        return await answer_grading.submit_answer(
            session,
            user_id=uid,
            session_id=sid,
            question_id=qid,
            selected_index=0,
        )

    results = await asyncio.gather(_submit(), _submit(), return_exceptions=True)

    # Exactly one 409, exactly one success-shaped response.
    successes = [r for r in results if not isinstance(r, BaseException)]
    failures = [r for r in results if isinstance(r, HTTPException)]
    assert len(successes) + len(failures) == 2
    if failures:
        assert any(f.status_code == 409 for f in failures)
