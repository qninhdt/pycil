"""The public model catalog endpoint.

The endpoint is the client's only source of truth for which models and reasoning
levels exist. Two properties matter: it must expose only what the server is
willing to run, and it must not leak anything a client could use to name a
credential or bypass the server's own pricing.
"""

from uuid import uuid4

import pytest

from pycil.auth.models import User
from pycil.product_config import system_config
from tests.support.clerk_jwks import bearer

pytestmark = pytest.mark.asyncio


async def _signed_in(client, session, clerk_stub):
    user = User(email=f"catalog-{uuid4()}@example.test", clerk_id=f"user_{uuid4().hex}")
    session.add(user)
    await session.commit()
    token = clerk_stub.token(subject=user.clerk_id, email=user.email)
    return bearer(token)


async def test_the_catalog_lists_the_enabled_models_and_the_default(client, session, clerk_stub):
    headers = await _signed_in(client, session, clerk_stub)

    response = await client.get("/v1/assistant/models", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["defaultModel"] == system_config.assistant.default_model
    assert body["defaultReasoningEffort"] == system_config.assistant.default_reasoning_effort

    ids = [model["id"] for model in body["models"]]
    assert ids == [model.id for model in system_config.enabled_models()]
    assert system_config.assistant.default_model in ids
    # A disabled catalog entry is a considered model kept on record, not an offer.
    assert "claude-3-7-sonnet" not in ids


async def test_the_catalog_exposes_capabilities_and_prices_but_no_credentials(
    client, session, clerk_stub
):
    headers = await _signed_in(client, session, clerk_stub)

    body = (await client.get("/v1/assistant/models", headers=headers)).json()
    model = body["models"][0]

    assert set(model) == {
        "id",
        "name",
        "provider",
        "vision",
        "reasoning",
        "supportedEfforts",
        "contextWindow",
        "maxOutputTokens",
        "pricing",
        "isDefault",
    }
    assert set(model["pricing"]) == {
        "inputUsdPerM",
        "outputUsdPerM",
        "cachedReadUsdPerM",
    }
    # Nothing in the payload may name a secret or a route to the provider.
    import json

    serialized = json.dumps(body)
    for forbidden in ("api_key", "apiKey", "base_url", "baseUrl", "secret"):
        assert forbidden not in serialized


async def test_the_default_model_is_flagged_exactly_once(client, session, clerk_stub):
    headers = await _signed_in(client, session, clerk_stub)

    body = (await client.get("/v1/assistant/models", headers=headers)).json()

    flagged = [model["id"] for model in body["models"] if model["isDefault"]]
    assert flagged == [body["defaultModel"]]


async def test_an_anonymous_caller_cannot_read_the_catalog(client):
    """The catalog is product policy, not public data."""
    response = await client.get("/v1/assistant/models")

    assert response.status_code == 401
