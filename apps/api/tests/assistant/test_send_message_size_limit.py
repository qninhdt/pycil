"""The oversized-message guard is a client payload error at the wire."""

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.config import settings
from pycil.db.session import get_session
from pycil.main import create_app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def message_client(engine, monkeypatch):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_session():
        async with factory() as session:
            yield session

    async def override_user() -> CurrentUser:
        return CurrentUser(id=uuid4(), email="oversized@example.test")

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[current_user] = override_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_an_oversized_message_is_rejected_as_a_client_payload_error(
    message_client, monkeypatch
):
    client = message_client
    monkeypatch.setattr(settings, "assistant_max_message_chars", 8)

    response = await client.post(
        f"/v1/assistant/threads/{uuid4()}/messages",
        json={"clientMessageId": str(uuid4()), "content": "x" * 9},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "assistant_message_too_long"
