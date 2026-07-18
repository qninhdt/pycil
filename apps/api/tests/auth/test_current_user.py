"""current_user dependency: token-version revocation (DB-backed)."""

import pytest

from pycil.auth import tokens
from pycil.auth.models import User

pytestmark = pytest.mark.asyncio


async def _seed(session, **kw) -> User:
    user = User(email=kw.pop("email", "u@x.co"), **kw)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_valid_token_authenticates(client, session):
    user = await _seed(session)
    token, _ = tokens.sign_access(user)
    resp = await client.post("/v1/auth/refresh", headers=await _bearer(token))
    assert resp.status_code == 200


async def test_missing_token_401(client):
    resp = await client.post("/v1/auth/refresh")
    assert resp.status_code == 401


async def test_token_version_bump_revokes(client, session):
    user = await _seed(session, email="rev@x.co", token_version=0)
    token, _ = tokens.sign_access(user)  # embeds tv=0
    user.token_version = 1
    await session.commit()
    resp = await client.post("/v1/auth/refresh", headers=await _bearer(token))
    assert resp.status_code == 401
