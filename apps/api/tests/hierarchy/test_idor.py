"""IDOR: a user cannot read/write another user's private node via the HTTP API."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.auth.deps import current_user
from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.db.session import get_session
from pycil.hierarchy.application import service
from pycil.hierarchy.infra.models import NodeType, Visibility
from pycil.main import create_app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def two_user_client(engine):
    """Client whose authenticated user is swappable via app.state._as_user."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_session():
        async with factory() as s:
            yield s

    app = create_app()
    app.dependency_overrides[get_session] = _override_session

    holder = {"user": None}

    async def _override_user() -> CurrentUser:
        return holder["user"]

    app.dependency_overrides[current_user] = _override_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, factory, holder


def _cu(u: User) -> CurrentUser:
    return CurrentUser(id=u.id, email=u.email)


async def test_non_owner_cannot_read_private_node(two_user_client):
    client, factory, holder = two_user_client
    async with factory() as s:
        owner = User(email="owner@x.co")
        attacker = User(email="attacker@x.co")
        s.add_all([owner, attacker])
        await s.commit()
        await s.refresh(owner)
        await s.refresh(attacker)
        deck = await service.create_node(s, owner.id, node_type=NodeType.DECK, name="secret")

    # Attacker tries to read the owner's PRIVATE folder stats.
    holder["user"] = _cu(attacker)
    resp = await client.get(f"/v1/folders/{deck.id}/stats")
    # Private node existence not leaked → 404.
    assert resp.status_code == 404


async def test_non_owner_cannot_write_node(two_user_client):
    client, factory, holder = two_user_client
    async with factory() as s:
        owner = User(email="owner2@x.co")
        attacker = User(email="attacker2@x.co")
        s.add_all([owner, attacker])
        await s.commit()
        await s.refresh(owner)
        await s.refresh(attacker)
        deck = await service.create_node(s, owner.id, node_type=NodeType.DECK, name="d")

    holder["user"] = _cu(attacker)
    resp = await client.delete(f"/v1/nodes/{deck.id}")
    assert resp.status_code == 403


async def test_public_node_readable_not_writable_by_non_owner(two_user_client):
    client, factory, holder = two_user_client
    async with factory() as s:
        owner = User(email="owner3@x.co")
        other = User(email="other3@x.co")
        s.add_all([owner, other])
        await s.commit()
        await s.refresh(owner)
        await s.refresh(other)
        deck = await service.create_node(
            s, owner.id, node_type=NodeType.DECK, name="pub", visibility=Visibility.PUBLIC
        )

    holder["user"] = _cu(other)
    # Public node: readable by non-owner.
    read = await client.get(f"/v1/folders/{deck.id}/stats")
    assert read.status_code == 200
    # But NOT writable by non-owner.
    write = await client.delete(f"/v1/nodes/{deck.id}")
    assert write.status_code == 403


async def test_anonymous_can_read_public_node_but_not_private_node(two_user_client):
    client, factory, _ = two_user_client
    async with factory() as s:
        owner = User(email="anonymous-owner@x.co")
        s.add(owner)
        await s.commit()
        await s.refresh(owner)
        public = await service.create_node(
            s,
            owner.id,
            node_type=NodeType.DECK,
            name="public direct link",
            visibility=Visibility.PUBLIC,
        )
        private = await service.create_node(
            s, owner.id, node_type=NodeType.DECK, name="private direct link"
        )

    public_response = await client.get(f"/v1/nodes/{public.id}")
    private_response = await client.get(f"/v1/nodes/{private.id}")

    assert public_response.status_code == 200
    assert public_response.json()["id"] == str(public.id)
    assert private_response.status_code == 404


async def test_owner_can_read_and_write(two_user_client):
    client, factory, holder = two_user_client
    async with factory() as s:
        owner = User(email="owner4@x.co")
        s.add(owner)
        await s.commit()
        await s.refresh(owner)
        deck = await service.create_node(s, owner.id, node_type=NodeType.DECK, name="mine")

    holder["user"] = _cu(owner)
    assert (await client.get(f"/v1/folders/{deck.id}/stats")).status_code == 200
    assert (await client.delete(f"/v1/nodes/{deck.id}")).status_code == 204
