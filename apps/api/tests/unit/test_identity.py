from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.ext.asyncio import async_sessionmaker

from pycil.account.auth import Actor, ActorContext, Identity
from pycil.http import Problem
from pycil.main import create_app


@pytest.fixture
def signed_identity(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    identity = Identity(
        SimpleNamespace(
            clerk_jwks_url="https://example.invalid/jwks",
            clerk_issuer="https://issuer.example.invalid",
            clerk_audience="pycil",
        )
    )
    monkeypatch.setattr(
        identity.keys,
        "get_signing_key_from_jwt",
        lambda token: SimpleNamespace(key=private.public_key()),
    )
    return identity, private


def claims():
    return {
        "sub": "user_secure",
        "iss": "https://issuer.example.invalid",
        "aud": "pycil",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }


async def test_clerk_subject_requires_actual_signature_and_claims(signed_identity):
    identity, key = signed_identity
    token = jwt.encode(claims(), key, algorithm="RS256")
    assert await identity.subject(token) == "user_secure"
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(Problem, match="invalid_credentials"):
        await identity.subject(jwt.encode(claims(), other, algorithm="RS256"))


@pytest.mark.parametrize(
    "change",
    [
        {"iss": "https://attacker.invalid"},
        {"aud": "other"},
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
        {"sub": ""},
        {"sub": 12},
    ],
)
async def test_wrong_identity_claims_rejected(signed_identity, change):
    identity, key = signed_identity
    with pytest.raises(Problem, match="invalid_credentials"):
        await identity.subject(jwt.encode(claims() | change, key, algorithm="RS256"))


async def test_missing_subject_cannot_claim_an_account(signed_identity):
    identity, key = signed_identity
    values = claims()
    values.pop("sub")
    with pytest.raises(Problem, match="invalid_credentials"):
        await identity.subject(jwt.encode(values, key, algorithm="RS256"))


async def test_bearer_http_auth_verifies_token_before_reading_cached_user(signed_identity, config):
    identity, key = signed_identity
    now = datetime.now(UTC)
    user = ActorContext(
        id=uuid4(),
        clerk_subject="user_secure",
        display_name=None,
        plan="FREE",
        settings={},
        cycle_anchor=now,
        created_at=now,
    )
    cache = SimpleNamespace(get=AsyncMock(return_value=user))
    app = create_app()
    app.state.product = config
    app.state.deployment = SimpleNamespace(allowed_origins=["https://client.invalid"])
    app.state.sessions = async_sessionmaker(info={"cache": cache})
    app.state.identity = identity

    @app.get("/test-session")
    async def session(user: Actor):
        return {"id": str(user.id)}

    token = jwt.encode(claims(), key, algorithm="RS256")
    expired = jwt.encode(claims() | {"exp": now - timedelta(minutes=1)}, key, algorithm="RS256")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="https://api.invalid"
    ) as client:
        response = await client.get("/test-session", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json() == {"id": str(user.id)}
        for headers in [
            {},
            {"Authorization": "Bearer invalid"},
            {"Authorization": f"Bearer {expired}"},
        ]:
            response = await client.get("/test-session", headers=headers)
            assert response.status_code == 401
            assert response.headers["www-authenticate"] == "Bearer"
    cache.get.assert_awaited_once_with("actor:v2:user_secure", ActorContext)
