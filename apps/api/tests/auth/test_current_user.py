"""Refresh-token rotation and token-version revocation."""

import pytest

from pycil.auth import tokens
from pycil.auth.models import User
from pycil.auth.refresh_sessions import issue

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def default_access_token_ttl(monkeypatch):
    """Keep auth-contract tests independent from local developer configuration."""
    monkeypatch.setattr(tokens.settings, "jwt_max_age_seconds", 900)


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
    raw_refresh, _ = await issue(session, user.id)
    await session.commit()
    resp = await client.post("/v1/auth/refresh", json={"refresh_token": raw_refresh})
    assert resp.status_code == 200
    body = resp.json()
    # camelCase on the wire: the response DTOs carry serialization_alias so the
    # client does not have to transform bodies to find its own fields.
    assert body["accessToken"]
    assert body["refreshToken"] != raw_refresh
    assert body["tokenType"] == "bearer"
    assert body["expiresIn"] == 900
    assert body["refreshExpiresIn"] > 0


async def test_missing_token_401(client):
    resp = await client.post("/v1/auth/refresh")
    assert resp.status_code == 401


async def test_token_version_bump_revokes(client, session):
    user = await _seed(session, email="rev@x.co", token_version=0)
    token, _ = tokens.sign_access(user)  # embeds tv=0
    user.token_version = 1
    await session.commit()
    resp = await client.get("/v1/me", headers=await _bearer(token))
    assert resp.status_code == 401


async def test_reused_refresh_token_revokes_the_new_access_token(client, session):
    user = await _seed(session, email="replay@x.co")
    raw_refresh, _ = await issue(session, user.id)
    await session.commit()

    first = await client.post("/v1/auth/refresh", json={"refresh_token": raw_refresh})
    assert first.status_code == 200
    new_access = first.json()["accessToken"]

    replay = await client.post("/v1/auth/refresh", json={"refresh_token": raw_refresh})
    assert replay.status_code == 401
    revoked = await client.get("/v1/me", headers=await _bearer(new_access))
    assert revoked.status_code == 401


async def test_logout_is_idempotent_and_revokes_access(client, session):
    user = await _seed(session, email="logout@x.co")
    access, _ = tokens.sign_access(user)
    raw_refresh, _ = await issue(session, user.id)
    await session.commit()

    first = await client.post("/v1/auth/logout", json={"refresh_token": raw_refresh})
    second = await client.post("/v1/auth/logout", json={"refresh_token": raw_refresh})
    assert first.status_code == 204
    assert second.status_code == 204
    assert (await client.get("/v1/me", headers=await _bearer(access))).status_code == 401
