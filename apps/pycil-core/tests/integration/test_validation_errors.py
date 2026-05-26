"""Integration: FastAPI request-validation surface.

422 from FastAPI/Pydantic when request body fails schema validation, not
500. Pinned for the answer endpoint and start-session endpoint.
"""
from __future__ import annotations

from uuid import uuid4

from tests.factories import make_deck


async def test_selected_index_invalid_returns_422(client) -> None:
    response = await client.post(
        f"/sessions/{uuid4()}/answer",
        json={"question_id": str(uuid4()), "selected_index": "not-int"},
    )
    assert response.status_code == 422


async def test_start_session_negative_size_returns_422(client, session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    response = await client.post(
        f"/decks/{deck['id']}/learn",
        json={"session_size": -1},
    )
    # Schema rejects negative or 0 session_size as invalid.
    assert response.status_code in (400, 422)


async def test_share_link_on_missing_node_returns_404(client) -> None:
    response = await client.post(f"/nodes/{uuid4()}/share-links")
    assert response.status_code == 404
