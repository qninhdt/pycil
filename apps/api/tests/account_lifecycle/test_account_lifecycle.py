"""Account export/deletion remain scoped to Pycil-owned data."""

import pytest
from sqlalchemy import text

from pycil.auth import tokens
from pycil.auth.models import User
from pycil.auth.refresh_sessions import issue
from pycil.hierarchy.models import Node, NodeType, Visibility

pytestmark = pytest.mark.asyncio


async def _seed(session) -> User:
    user = User(email="account@x.co")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_export_and_delete_remove_only_the_authenticated_user(client, session):
    owner = await _seed(session)
    other = User(email="other@x.co")
    session.add(other)
    await session.flush()
    session.add(Node(author_id=owner.id, type=NodeType.FOLDER, name="Owner folder"))
    session.add(Node(author_id=other.id, type=NodeType.FOLDER, name="Other folder"))
    raw_refresh, _ = await issue(session, owner.id)
    await session.commit()
    access, _ = tokens.sign_access(owner)

    exported = await client.get("/v1/me/export", headers=await _headers(access))
    assert exported.status_code == 200
    assert exported.json()["profile"]["email"] == owner.email
    assert [item["name"] for item in exported.json()["hierarchy"]] == ["Owner folder"]

    deleted = await client.request(
        "DELETE",
        "/v1/me",
        headers=await _headers(access),
        json={"refresh_token": raw_refresh, "confirmation": "DELETE"},
    )
    assert deleted.status_code == 204
    count_sql = text("SELECT count(*) FROM users WHERE id = :id")
    assert await session.scalar(count_sql, {"id": owner.id}) == 0
    assert await session.scalar(count_sql, {"id": other.id}) == 1


async def test_delete_requires_literal_confirmation(client, session):
    user = await _seed(session)
    raw_refresh, _ = await issue(session, user.id)
    await session.commit()
    access, _ = tokens.sign_access(user)

    response = await client.request(
        "DELETE",
        "/v1/me",
        headers=await _headers(access),
        json={"refresh_token": raw_refresh, "confirmation": "delete"},
    )
    assert response.status_code == 401
    assert await session.get(User, user.id) is not None


async def test_delete_removes_cross_owner_reference_to_deleted_public_deck(client, session):
    owner = await _seed(session)
    other = User(email="reference-owner@x.co")
    session.add(other)
    await session.flush()
    deck = Node(
        author_id=owner.id,
        type=NodeType.DECK,
        name="Public deck",
        visibility=Visibility.PUBLIC,
    )
    session.add(deck)
    await session.flush()
    reference = Node(
        author_id=other.id,
        type=NodeType.REFERENCE,
        name="External reference",
        target_node_id=deck.id,
    )
    session.add(reference)
    raw_refresh, _ = await issue(session, owner.id)
    await session.commit()
    access, _ = tokens.sign_access(owner)
    reference_id = reference.id

    response = await client.request(
        "DELETE",
        "/v1/me",
        headers=await _headers(access),
        json={"refresh_token": raw_refresh, "confirmation": "DELETE"},
    )

    assert response.status_code == 204
    assert await session.get(User, other.id) is not None
    session.expire_all()
    assert await session.get(Node, reference_id) is None
