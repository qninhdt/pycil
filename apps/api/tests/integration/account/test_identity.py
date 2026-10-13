import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import SecretStr
from sqlalchemy import func, select

from pycil.account.auth import actor, optional_actor
from pycil.account.models import User
from pycil.app.config import load_config
from pycil.app.http import Problem
from pycil.infrastructure.cache import RedisCache
from pycil.infrastructure.clerk import Identity
from pycil.library.models import Node, NodePath


async def test_verified_identity_provisions_once_and_invalid_tokens_cannot_use_cache(
    database, redis_store, monkeypatch
):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    deployment = SimpleNamespace(
        clerk_jwks_url="https://identity.invalid/jwks",
        clerk_issuer="https://identity.invalid",
        clerk_audience="pycil",
        clerk_secret_key=SecretStr("test-only"),
    )
    identity = Identity(deployment)
    # Only key retrieval is substituted; JWT validation stays real.
    monkeypatch.setattr(
        identity.keys,
        "get_signing_key_from_jwt",
        lambda token: SimpleNamespace(key=private_key.public_key()),
    )
    claims = {
        "sub": "user_verified",
        "iss": deployment.clerk_issuer,
        "aud": deployment.clerk_audience,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    token = jwt.encode(claims, private_key, algorithm="RS256")
    redis, namespace = redis_store
    cache = RedisCache(redis, namespace)
    calls = 0
    both_requested = asyncio.Event()

    async def profile(request):
        nonlocal calls
        calls += 1
        if calls == 2:
            both_requested.set()
        await asyncio.wait_for(both_requested.wait(), timeout=5)
        return httpx.Response(200, json={"first_name": "A", "last_name": "Learner"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(profile)) as http:
        state = SimpleNamespace(
            identity=identity, deployment=deployment, http=http, product=load_config()
        )

        async def authenticate(value):
            request = Request(
                {
                    "type": "http",
                    "headers": [(b"authorization", b"Bearer " + value.encode())],
                    "app": SimpleNamespace(state=state),
                }
            )
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=value)
            async with database.sessions() as session:
                session.info["cache"] = cache
                return await actor(request, session, credentials)

        first, second = await asyncio.gather(authenticate(token), authenticate(token))
        assert first.id == second.id
        assert first.display_name == "A Learner"
        assert (await authenticate(token)).id == first.id
        assert calls == 2
        async with database.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(User)) == 1
            assert await session.scalar(select(func.count()).select_from(Node)) == 3
            assert await session.scalar(select(func.count()).select_from(NodePath)) == 5
        for replacement in (
            {"iss": "https://wrong.invalid"},
            {"aud": "another-app"},
            {"exp": datetime.now(UTC) - timedelta(minutes=1)},
        ):
            invalid = jwt.encode(claims | replacement, private_key, algorithm="RS256")
            with pytest.raises(Problem) as error:
                await authenticate(invalid)
            assert error.value.status == 401
        forged_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with pytest.raises(Problem) as error:
            await authenticate(jwt.encode(claims, forged_key, algorithm="RS256"))
        assert error.value.status == 401
        assert calls == 2


@pytest.mark.parametrize("status, expected", [(404, 401), (503, 503), (200, 503)])
async def test_remote_identity_failure_does_not_create_accounts(database, status, expected):
    class VerifiedSubject:
        async def subject(self, token):
            return "user_missing"

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=["invalid"]))
    ) as http:
        state = SimpleNamespace(
            identity=VerifiedSubject(),
            http=http,
            deployment=SimpleNamespace(clerk_secret_key=SecretStr("test-only")),
        )
        request = Request(
            {
                "type": "http",
                "headers": [(b"authorization", b"Bearer verified")],
                "app": SimpleNamespace(state=state),
            }
        )
        async with database.sessions() as session:
            with pytest.raises(Problem) as error:
                await optional_actor(
                    request,
                    session,
                    HTTPAuthorizationCredentials(scheme="Bearer", credentials="verified"),
                )
            assert error.value.status == expected
        async with database.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(User)) == 0
            assert await session.scalar(select(func.count()).select_from(Node)) == 0
