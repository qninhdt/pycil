"""Authorization edges on `learning_service`.

Pinned:
- Cross-user submit on a valid session_id → 403 `session_forbidden`.
- 403 body matches the structure of 404 (no oracle for session_id existence).
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from pycil_core.services import learning_service as ls
from tests.factories import make_session_state


async def test_submit_wrong_user_403(session, fakeredis_client, test_user, second_user) -> None:
    sid = str(uuid4())
    state = make_session_state(
        session_id=sid,
        user_id=test_user["id"],
        deck_id=uuid4(),
        definition_ids=[1],
        current_question_id=str(uuid4()),
        current_definition_id=1,
    )
    await ls._save_state(fakeredis_client, sid, state)

    with pytest.raises(HTTPException) as exc:
        await ls.submit_answer(
            session,
            user_id=second_user["id"],
            session_id=sid,
            question_id=UUID(state["current_question_id"]),
            selected_index=0,
        )
    assert exc.value.status_code == 403
    assert "session_forbidden" in str(exc.value.detail)


async def test_submit_with_question_mismatch_409(
    session, fakeredis_client, test_user
) -> None:
    sid = str(uuid4())
    state = make_session_state(
        session_id=sid,
        user_id=test_user["id"],
        deck_id=uuid4(),
        definition_ids=[1],
        current_question_id=str(uuid4()),
        current_definition_id=1,
    )
    await ls._save_state(fakeredis_client, sid, state)

    # Stale question_id (not the current one).
    with pytest.raises(HTTPException) as exc:
        await ls.submit_answer(
            session,
            user_id=UUID(str(test_user["id"])),
            session_id=sid,
            question_id=uuid4(),
            selected_index=0,
        )
    assert exc.value.status_code == 409
