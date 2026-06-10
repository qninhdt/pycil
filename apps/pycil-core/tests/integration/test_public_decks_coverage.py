"""Public deck browse + clone endpoint coverage.

Pins:
- GET /public/decks lists only PUBLIC, non-deleted DECK nodes (no auth)
- term_count / clone_count aggregates
- pagination cursor (next_cursor round-trips, limit honored)
- invalid cursor → 400
- q search filter (pg_trgm `%` operator)
- GET /public/decks/{id} 200 snapshot / 404 for private/missing/folder
- POST /public/decks/{id}/clone happy path + 404 for private source
"""
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text

from tests.factories import (
    attach_definition_to_deck,
    make_deck,
    make_definition,
    make_term,
)


async def _public_deck(session, author_id, name="Public Deck"):
    return await make_deck(
        session, author_id=author_id, name=name, visibility="PUBLIC"
    )


# --------------------------------------------------------------------------- #
# GET /public/decks
# --------------------------------------------------------------------------- #

async def test_list_public_decks_only_public(client, session, test_user, second_user):
    pub = await _public_deck(session, second_user["id"], name="Visible")
    await make_deck(session, author_id=second_user["id"], name="Hidden")  # PRIVATE

    resp = await client.get("/public/decks")
    assert resp.status_code == 200
    body = resp.json()
    ids = {d["id"] for d in body["decks"]}
    assert str(pub["id"]) in ids
    names = {d["name"] for d in body["decks"]}
    assert "Hidden" not in names
    assert body["next_cursor"] is None


async def test_list_public_decks_excludes_soft_deleted(client, session, second_user):
    pub = await _public_deck(session, second_user["id"], name="Gone")
    await session.execute(
        text("UPDATE nodes SET deleted_at = NOW() WHERE id = :id"),
        {"id": pub["id"]},
    )
    await session.commit()
    resp = await client.get("/public/decks")
    assert resp.status_code == 200
    assert resp.json()["decks"] == []


async def test_list_public_decks_term_and_clone_counts(
    client, session, test_user, second_user
):
    pub = await _public_deck(session, second_user["id"])
    term_id = await make_term(session, value="counted-term")
    def_id = await make_definition(session, term_id=term_id)
    await attach_definition_to_deck(session, deck_id=pub["id"], definition_id=def_id)
    # Record a clone for clone_count.
    cloned = await make_deck(session, author_id=test_user["id"], name="Clone")
    await session.execute(
        text(
            "INSERT INTO deck_clones (source_deck_id, cloned_deck_id, cloned_by_user) "
            "VALUES (:s, :c, :u)"
        ),
        {"s": pub["id"], "c": cloned["id"], "u": test_user["id"]},
    )
    await session.commit()

    resp = await client.get("/public/decks")
    assert resp.status_code == 200
    deck = next(d for d in resp.json()["decks"] if d["id"] == str(pub["id"]))
    assert deck["term_count"] == 1
    assert deck["clone_count"] == 1


async def test_list_public_decks_pagination_cursor(client, session, second_user):
    # Three public decks; limit=2 should yield a next_cursor and 2 rows.
    for i in range(3):
        await _public_deck(session, second_user["id"], name=f"Deck-{i}")
    page1 = await client.get("/public/decks", params={"limit": 2})
    assert page1.status_code == 200
    body1 = page1.json()
    assert len(body1["decks"]) == 2
    assert body1["next_cursor"] is not None

    page2 = await client.get(
        "/public/decks", params={"limit": 2, "cursor": body1["next_cursor"]}
    )
    assert page2.status_code == 200
    body2 = page2.json()
    assert len(body2["decks"]) == 1
    assert body2["next_cursor"] is None
    # No overlap across pages.
    p1_ids = {d["id"] for d in body1["decks"]}
    p2_ids = {d["id"] for d in body2["decks"]}
    assert p1_ids.isdisjoint(p2_ids)


async def test_list_public_decks_invalid_cursor_400(client, session):
    resp = await client.get("/public/decks", params={"cursor": "!!!not-base64!!!"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid_cursor"


async def test_list_public_decks_q_filter(client, session, second_user):
    await _public_deck(session, second_user["id"], name="Spanish Vocabulary")
    await _public_deck(session, second_user["id"], name="French Grammar")
    resp = await client.get("/public/decks", params={"q": "Spanish Vocabulary"})
    assert resp.status_code == 200
    names = {d["name"] for d in resp.json()["decks"]}
    assert "Spanish Vocabulary" in names
    assert "French Grammar" not in names


# --------------------------------------------------------------------------- #
# GET /public/decks/{id}
# --------------------------------------------------------------------------- #

async def test_get_public_deck_ok(client, session, second_user):
    pub = await _public_deck(session, second_user["id"], name="Detail")
    resp = await client.get(f"/public/decks/{pub['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(pub["id"])
    assert body["name"] == "Detail"
    assert "updated_at" in body


async def test_get_public_deck_private_404(client, session, second_user):
    priv = await make_deck(session, author_id=second_user["id"], visibility="PRIVATE")
    resp = await client.get(f"/public/decks/{priv['id']}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "deck_not_found"


async def test_get_public_deck_missing_404(client, session):
    resp = await client.get(f"/public/decks/{uuid4()}")
    assert resp.status_code == 404


async def test_get_public_deck_folder_404(client, session, second_user):
    # A PUBLIC folder is not a deck → 404.
    row = (
        await session.execute(
            text(
                "INSERT INTO nodes (author_id, type, name, visibility) "
                "VALUES (:aid, 'FOLDER', 'f', 'PUBLIC') RETURNING id"
            ),
            {"aid": second_user["id"]},
        )
    ).one()
    await session.commit()
    resp = await client.get(f"/public/decks/{row.id}")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# POST /public/decks/{id}/clone
# --------------------------------------------------------------------------- #

async def test_clone_public_deck_ok(client, session, second_user):
    pub = await _public_deck(session, second_user["id"], name="Cloneable")
    resp = await client.post(f"/public/decks/{pub['id']}/clone")
    assert resp.status_code == 200
    new_id = resp.json()["new_deck_id"]
    assert new_id
    # New deck owned by the test_user (the client's authed user).
    row = (
        await session.execute(
            text("SELECT visibility::text AS v FROM nodes WHERE id = :id"),
            {"id": new_id},
        )
    ).one()
    assert row.v == "PRIVATE"


async def test_clone_private_deck_404(client, session, second_user):
    priv = await make_deck(session, author_id=second_user["id"], visibility="PRIVATE")
    resp = await client.post(f"/public/decks/{priv['id']}/clone")
    assert resp.status_code == 404
