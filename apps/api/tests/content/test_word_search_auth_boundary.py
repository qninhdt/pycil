"""``GET /v1/words/search`` reads like every other public content route.

Anonymous lookup is deliberate — a shared deck opens from its own link without an
account — so this route is not sign-in-only. What it lacked was any auth
dependency at all, which made it the single route in the API where a supplied
credential was never examined: a revoked or forged token was treated exactly like
no token.

The dependency is what closes that. It also puts the route back on the same
convention as its two neighbours (``/v1/senses/{id}``, ``/v1/decks/{id}/items``),
so "which access level does this route use" has one answer everywhere.
"""

from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.auth import tokens
from pycil.auth.models import User
from pycil.db.session import get_session
from pycil.main import create_app
from pycil.ports.lexi_provider import get_lexi_client

pytestmark = pytest.mark.asyncio


class FakeReader:
    """One search hit whose entry lookup either works or raises."""

    def __init__(self, *, entry_fails: bool = False):
        self.entry_fails = entry_fails

    async def search(self, _query):
        return [
            SimpleNamespace(
                display="eloquent",
                entry_type="word",
                score=1.0,
                lexi_word_id=42,
                cambridge_id=None,
                gloss=None,
                pos=None,
            )
        ]

    async def get_entry(self, _word_id):
        if self.entry_fails:
            raise RuntimeError("lexi unavailable")
        return SimpleNamespace(
            word_id=42,
            senses=[
                SimpleNamespace(
                    sense_id=9001,
                    definition="fluent and persuasive",
                    tier="core",
                    pos="adjective",
                    cefr_level="C1",
                    examples=[],
                    word="eloquent",
                    word_id=42,
                )
            ],
        )


@pytest.fixture
async def search_client(engine, request):
    """A real app, so the route's own dependency runs rather than an override."""
    reader = getattr(request, "param", None) or FakeReader()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_session():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_lexi_client] = lambda: reader
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory, reader


async def test_an_anonymous_visitor_can_still_look_a_word_up(search_client):
    client, _factory, _reader = search_client

    response = await client.get("/v1/words/search", params={"q": "eloquent"})

    assert response.status_code == 200
    assert [row["display"] for row in response.json()] == ["eloquent"]


async def test_a_signed_in_caller_gets_the_same_results(search_client):
    client, factory, _reader = search_client
    async with factory() as session:
        user = User(email="searcher@example.test")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    access, _ = tokens.sign_access(user)

    response = await client.get(
        "/v1/words/search",
        params={"q": "eloquent"},
        headers={"Authorization": f"Bearer {access}"},
    )

    assert response.status_code == 200
    assert [row["display"] for row in response.json()] == ["eloquent"]


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJub3BlIn0.zzzzzzzzzzzzzzzzzzzzzzzzzzzz",
    ],
)
async def test_a_broken_token_is_rejected_rather_than_read_as_anonymous(search_client, token):
    """The behaviour change worth guarding.

    With no dependency the header was never parsed, so a forged or revoked token
    searched happily as a guest. Failing closed is what makes the credential mean
    something on this route.
    """
    client, _factory, _reader = search_client

    response = await client.get(
        "/v1/words/search",
        params={"q": "eloquent"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


async def test_a_revoked_token_cannot_search(search_client):
    """A token whose `tv` no longer matches the user's is revoked, not anonymous."""
    client, factory, _reader = search_client
    async with factory() as session:
        user = User(email="revoked-searcher@example.test")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        access, _ = tokens.sign_access(user)
        user.token_version += 1
        await session.commit()

    response = await client.get(
        "/v1/words/search",
        params={"q": "eloquent"},
        headers={"Authorization": f"Bearer {access}"},
    )

    assert response.status_code == 401


@pytest.mark.parametrize("search_client", [FakeReader(entry_fails=True)], indirect=True)
async def test_one_result_losing_its_entry_still_returns_a_usable_row(search_client, caplog):
    """A Lexi outage used to report itself as a successful search with thin results.

    The row is still worth returning — it carries the headword — so the response is
    not abandoned. What changed is that the failure is now recorded instead of
    silently swallowed.
    """
    import logging

    client, _factory, _reader = search_client

    with caplog.at_level(logging.WARNING, logger="pycil.content.router"):
        response = await client.get("/v1/words/search", params={"q": "eloquent"})

    assert response.status_code == 200
    body = response.json()
    assert [row["display"] for row in body] == ["eloquent"]
    assert body[0]["senses"] == []
    assert any("enrichment failed" in record.message for record in caplog.records)
    # The learner's query is not an operational detail worth persisting in logs.
    assert not any("eloquent" in record.getMessage() for record in caplog.records)
