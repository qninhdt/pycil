"""Integration: end-to-end learning session flow.

POST start → GET question → POST answer → state shifts.
"""
from __future__ import annotations

from tests.factories import (
    attach_definition_to_deck,
    make_deck,
    make_definition,
    make_mcq_question,
    make_term,
)


async def test_start_session_returns_201(client, session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    tid = await make_term(session, value="e2e-1")
    did = await make_definition(session, term_id=tid)
    await attach_definition_to_deck(
        session, deck_id=deck["id"], definition_id=did
    )
    await make_mcq_question(session, definition_id=did, correct_index=0)

    response = await client.post(
        f"/decks/{deck['id']}/learn",
        json={"session_size": 1},
    )
    assert response.status_code == 201
    body = response.json()
    assert "session_id" in body
    assert body["selected_count"] == 1


async def test_start_session_404_for_unknown_deck(client) -> None:
    from uuid import uuid4
    response = await client.post(
        f"/decks/{uuid4()}/learn",
        json={"session_size": 1},
    )
    assert response.status_code == 404
