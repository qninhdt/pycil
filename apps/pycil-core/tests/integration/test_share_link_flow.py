"""Integration: share-link create + revoke + 404 after revoke."""
from __future__ import annotations

from tests.factories import make_deck


async def test_share_link_create_then_revoke(client, session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])

    create_resp = await client.post(f"/nodes/{deck['id']}/share-links")
    assert create_resp.status_code == 200
    body = create_resp.json()
    assert "token" in body
    assert "id" in body
    link_id = body["id"]

    # Revoke.
    revoke_resp = await client.delete(f"/nodes/share-links/{link_id}")
    assert revoke_resp.status_code == 200
    assert revoke_resp.json() == {"revoked": True}

    # Second revoke returns 404 link_not_found.
    second = await client.delete(f"/nodes/share-links/{link_id}")
    assert second.status_code == 404
