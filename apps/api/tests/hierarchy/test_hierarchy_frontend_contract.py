"""Reload-safe hierarchy routes required by the frontend."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.auth.deps import current_user
from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.db.session import get_session
from pycil.hierarchy.application import service
from pycil.hierarchy.infra.models import NodeType
from pycil.main import create_app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def hierarchy_client(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        owner = User(email="tree-owner@example.com")
        session.add(owner)
        await session.commit()
        await session.refresh(owner)

    async def override_session():
        async with factory() as session:
            yield session

    async def override_user() -> CurrentUser:
        return CurrentUser(id=owner.id, email=owner.email)

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[current_user] = override_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory, owner


async def test_tree_list_update_and_learning_settings_survive_reload(hierarchy_client):
    client, factory, owner = hierarchy_client
    async with factory() as session:
        folder = await service.create_node(
            session, owner.id, node_type=NodeType.FOLDER, name="root"
        )
        deck = await service.create_node(
            session,
            owner.id,
            node_type=NodeType.DECK,
            name="verbs",
            parent_node_id=folder.id,
            description="old description",
        )

    roots = await client.get("/v1/nodes")
    children = await client.get(f"/v1/nodes?parentNodeId={folder.id}")
    updated = await client.patch(
        f"/v1/nodes/{deck.id}", json={"name": "common verbs", "description": "daily"}
    )
    # Session shape is the caller's own, not the deck's: the same values apply
    # whichever node a session starts from.
    settings = await client.patch(
        "/v1/me/learning-settings",
        json={"targetWordsPerSession": 7, "maxQuestionsPerRound": 13},
    )
    settings_read = await client.get("/v1/me/learning-settings")

    assert roots.status_code == 200
    assert [item["id"] for item in roots.json()["items"]] == [str(folder.id)]
    assert children.status_code == 200
    assert [item["id"] for item in children.json()["items"]] == [str(deck.id)]
    # A deck row carries its size; a folder row does not pretend to.
    assert children.json()["items"][0]["itemCount"] == 0
    assert roots.json()["items"][0]["itemCount"] is None
    assert updated.json()["name"] == "common verbs"
    assert updated.json()["description"] == "daily"
    assert settings.json() == {"targetWordsPerSession": 7, "maxQuestionsPerRound": 13}
    # Survives the reload, which is the point of this test.
    assert settings_read.json() == {"targetWordsPerSession": 7, "maxQuestionsPerRound": 13}
