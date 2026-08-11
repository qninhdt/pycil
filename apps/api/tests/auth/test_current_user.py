"""Refresh-token rotation and token-version revocation."""

import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from redis.exceptions import RedisError
from sqlalchemy import select

from pycil.auth import refresh_sessions, tokens
from pycil.auth import router as auth_router
from pycil.auth.models import RefreshSession, User
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


async def test_refresh_reuse_grace_then_old_replay_revokes_the_family(client, session, monkeypatch):
    user = await _seed(session, email="replay@x.co")
    raw_refresh, _ = await issue(session, user.id)
    await session.commit()

    first = await client.post("/v1/auth/refresh", json={"refresh_token": raw_refresh})
    assert first.status_code == 200
    new_access = first.json()["accessToken"]

    within_grace = await client.post("/v1/auth/refresh", json={"refresh_token": raw_refresh})
    assert within_grace.status_code == 200
    assert within_grace.json()["refreshToken"] != raw_refresh

    future = datetime.now(UTC) + timedelta(seconds=61)
    monkeypatch.setattr(refresh_sessions, "_now", lambda: future)
    replay = await client.post("/v1/auth/refresh", json={"refresh_token": raw_refresh})
    assert replay.status_code == 401
    revoked = await client.get("/v1/me", headers=await _bearer(new_access))
    assert revoked.status_code == 401


async def test_overlapping_refresh_requests_share_one_rotation(client, session, monkeypatch):
    user = await _seed(session, email="refresh-race@x.co")
    raw_refresh, _ = await issue(session, user.id)
    await session.commit()

    started = asyncio.Event()
    release = asyncio.Event()
    original_rotate = refresh_sessions.rotate

    async def gated_rotate(db_session, raw_token):
        started.set()
        await release.wait()
        return await original_rotate(db_session, raw_token)

    monkeypatch.setattr(refresh_sessions, "rotate", gated_rotate)
    first_task = asyncio.create_task(
        client.post("/v1/auth/refresh", json={"refresh_token": raw_refresh})
    )
    await started.wait()
    second_task = asyncio.create_task(
        client.post("/v1/auth/refresh", json={"refresh_token": raw_refresh})
    )
    await asyncio.sleep(0)
    release.set()

    first, second = await asyncio.gather(first_task, second_task)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["refreshToken"] == second.json()["refreshToken"]

    # The outcome marker is for overlapping callers only. A later reuse still
    # reaches PostgreSQL and invokes the family-revocation policy after grace.
    monkeypatch.setattr(
        refresh_sessions,
        "_now",
        lambda: datetime.now(UTC) + timedelta(seconds=61),
    )
    replay = await client.post("/v1/auth/refresh", json={"refresh_token": raw_refresh})
    assert replay.status_code == 401
    revoked = await client.get("/v1/me", headers=await _bearer(first.json()["accessToken"]))
    assert revoked.status_code == 401


async def test_refresh_retry_recovers_after_post_commit_failure(client, session, monkeypatch):
    user = await _seed(session, email="refresh-recovery@x.co")
    raw_refresh, _ = await issue(session, user.id)
    await session.commit()

    original_rotate = refresh_sessions.rotate
    calls = 0

    async def flaky_rotate(db_session, raw_token):
        nonlocal calls
        calls += 1
        result = await original_rotate(db_session, raw_token)
        if calls == 1:
            raise RuntimeError("response lost after commit")
        return result

    monkeypatch.setattr(refresh_sessions, "rotate", flaky_rotate)
    with pytest.raises(RuntimeError, match="response lost after commit"):
        await client.post("/v1/auth/refresh", json={"refresh_token": raw_refresh})
    recovered = await client.post("/v1/auth/refresh", json={"refresh_token": raw_refresh})

    assert recovered.status_code == 200
    assert calls == 2


async def test_legacy_successor_is_not_fabricated_on_replay(client, session):
    user = await _seed(session, email="legacy-refresh@x.co")
    raw_refresh, _ = await issue(session, user.id)
    await session.flush()
    predecessor = (
        await session.execute(
            select(RefreshSession).where(
                RefreshSession.token_digest == refresh_sessions.token_digest(raw_refresh)
            )
        )
    ).scalar_one()
    legacy_raw = secrets.token_urlsafe(48)
    legacy = RefreshSession(
        id=uuid4(),
        user_id=user.id,
        family_id=predecessor.family_id,
        token_digest=refresh_sessions.token_digest(legacy_raw),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    session.add(legacy)
    await session.commit()
    predecessor.revoked_at = datetime.now(UTC)
    predecessor.replaced_by_id = legacy.id
    await session.commit()

    replay = await client.post("/v1/auth/refresh", json={"refresh_token": raw_refresh})
    assert replay.status_code == 401


async def test_refresh_returns_503_when_redis_coordination_fails(client, session, monkeypatch):
    user = await _seed(session, email="refresh-redis-down@x.co")
    raw_refresh, _ = await issue(session, user.id)
    await session.commit()

    class BrokenRedis:
        async def set(self, *args, **kwargs):
            del args, kwargs
            raise RedisError("redis is down")

    monkeypatch.setattr(auth_router, "get_redis", lambda: BrokenRedis())
    response = await client.post("/v1/auth/refresh", json={"refresh_token": raw_refresh})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"


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


async def test_logout_logs_a_failed_disconnect_instead_of_discarding_it(
    app, client, session, caplog
):
    """`disconnect_user` returns a bool that both callers used to throw away.

    The call is best-effort by design — revocation is already durable, so logout
    must still succeed — but silently dropping the result means an operator has no
    signal that sockets stayed open after a revocation. That is the window an
    already-issued 900s connection token keeps working in.

    The broker is substituted through `dependency_overrides` rather than by
    monkeypatching the name the router imported. That is the point of the port: the
    route asks for a `RealtimeControl`, so the test supplies one and no HTTP client
    is constructed anywhere in this run.
    """
    import logging

    from pycil.ports.centrifugo import get_centrifugo
    from tests.realtime.fakes import FakeRealtimeControl

    user = await _seed(session, email="logout-disconnect@x.co")
    raw_refresh, _ = await issue(session, user.id)
    await session.commit()

    unreachable = FakeRealtimeControl(disconnects=False)
    app.dependency_overrides[get_centrifugo] = lambda: unreachable

    with caplog.at_level(logging.WARNING, logger="pycil.auth.router"):
        response = await client.post("/v1/auth/logout", json={"refresh_token": raw_refresh})

    # Logout still succeeds: local revocation is authoritative.
    assert response.status_code == 204
    assert unreachable.disconnected == [
        str(user.id)
    ], "logout must ask the broker to close the revoked user's sockets"
    assert any(
        "disconnect" in record.message.lower() for record in caplog.records
    ), "a failed realtime disconnect must be logged, not discarded"
