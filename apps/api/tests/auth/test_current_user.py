"""current_user dependency: banned 403, tv revocation, role re-read (DB-backed)."""

import pytest

from pycil.auth import tokens
from pycil.auth.models import User, UserRole

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
    resp = await client.post("/auth/refresh", headers=await _bearer(token))
    assert resp.status_code == 200


async def test_missing_token_401(client):
    resp = await client.post("/auth/refresh")
    assert resp.status_code == 401


async def test_banned_user_403(client, session):
    import datetime

    user = await _seed(session, email="banned@x.co")
    token, _ = tokens.sign_access(user)
    # Ban after issuing the token — authoritative gate is the per-request DB read.
    user.banned_at = datetime.datetime.now(datetime.UTC)
    await session.commit()
    resp = await client.post("/auth/refresh", headers=await _bearer(token))
    assert resp.status_code == 403


async def test_token_version_bump_revokes(client, session):
    user = await _seed(session, email="rev@x.co", token_version=0)
    token, _ = tokens.sign_access(user)  # embeds tv=0
    user.token_version = 1
    await session.commit()
    resp = await client.post("/auth/refresh", headers=await _bearer(token))
    assert resp.status_code == 401


async def test_role_reread_from_db(client, session):
    # Token minted as user; promote in DB → refresh still works, role is re-read.
    user = await _seed(session, email="admin@x.co", role=UserRole.user)
    token, _ = tokens.sign_access(user)
    user.role = UserRole.admin
    await session.commit()
    resp = await client.post("/auth/refresh", headers=await _bearer(token))
    assert resp.status_code == 200
    # New token reflects the re-read admin role.
    new_claims = tokens.verify(resp.json()["access_token"])
    assert new_claims["role"] == "admin"
