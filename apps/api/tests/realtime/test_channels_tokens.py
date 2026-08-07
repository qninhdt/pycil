"""Realtime: owner-scoped user-limited channel naming and connection tokens."""

import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import jwt
import pytest
from shared.realtime import channels
from shared.realtime.payloads import GradingResult

from pycil.config import Settings, settings
from pycil.ports import centrifugo as client
from pycil.realtime.application.subscriptions import _resource_id
from pycil.realtime.router import realtime_token


def test_durable_channel_uses_only_an_opaque_task_id():
    uid = uuid.uuid4()
    assert channels.async_task(uid) == f"async:{uid}"


def test_default_public_sse_url_uses_caddy_ingress(monkeypatch):
    monkeypatch.delenv("CENTRIFUGO_PUBLIC_SSE_URL", raising=False)
    assert Settings(_env_file=None).centrifugo_public_sse_url == "https://localhost/connection/sse"


def test_channels_for_two_tasks_do_not_collide():
    a, b = uuid.uuid4(), uuid.uuid4()
    assert channels.async_task(a) != channels.async_task(b)


def test_the_builder_produces_a_channel_the_subscribe_proxy_accepts():
    """Check the two sides against each other, not against a literal.

    Two builders once produced `users:{uid}:jobs:{id}` and `users:{uid}:grading:{id}`
    while the proxy admitted only `async:<uuid>`, so every event published through
    them reached a channel no client could hold and the notification was silently
    lost. A test asserting the builder against a hardcoded string would not have
    caught it — both sides have to be exercised together.
    """
    task_id = uuid.uuid4()
    assert _resource_id(channels.async_task(task_id)) == task_id


@pytest.mark.parametrize(
    "channel",
    [
        "users:owner:jobs:abc#owner",
        "users:owner:grading:abc#owner",
        "async:not-a-uuid",
        "prefixed:async:00000000-0000-0000-0000-000000000000",
    ],
)
def test_the_proxy_rejects_every_channel_shape_no_client_can_hold(channel):
    assert _resource_id(channel) is None


def test_connection_token_has_user_and_auth_version_metadata():
    uid = uuid.uuid4()
    token, _expires_at = client.mint_connection_token(uid, token_version=7)
    claims = jwt.decode(
        token, settings.centrifugo_token_hmac_secret, algorithms=["HS256"]
    )
    assert claims["sub"] == str(uid)
    assert "exp" in claims and "iat" in claims
    assert claims["meta"]["tokenVersion"] == 7


def test_token_signed_with_centrifugo_secret_not_api_jwt_secret():
    uid = uuid.uuid4()
    token, _expires_at = client.mint_connection_token(uid, token_version=1)
    # Must NOT verify against the API's JWT secret — different key domain.
    import pytest

    with pytest.raises(jwt.PyJWTError):
        jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def test_centrifugo_config_enables_sse_proxy_and_recovery_only():
    config = Path(__file__).parents[4] / "centrifugo-config.json"
    value = config.read_text()
    assert '"name": "async"' in value
    assert '"subscribe_proxy_enabled": true' in value
    assert '"history_size": 1' in value
    assert '"force_recovery": true' in value
    assert '"sse"' in value
    # `authorize_subscription` reads `meta["tokenVersion"]` off the proxy body and
    # fails closed without it. Centrifugo does not forward connection meta by
    # default, so dropping this flag denies every subscribe with code 103 — which
    # is exactly how it shipped until the E2E suite caught it. No emulation
    # assertion here: v6 has no `emulation.enabled` (the handler is always
    # registered), and its routing is covered by the Caddyfile test below.
    assert '"include_connection_meta": true' in value


def test_caddy_exposes_sse_emulation_but_not_websocket_or_sockjs():
    caddyfile = (Path(__file__).parents[4] / "Caddyfile").read_text()
    assert "/connection/sse*" in caddyfile
    assert "/emulation*" in caddyfile
    assert "/connection/websocket" not in caddyfile
    assert "/connection/sockjs" not in caddyfile


def test_payload_serialization():
    grade = GradingResult(
        response_id="r1", sense_id=42, is_correct=True, grade_score=1.0,
        mastery_before=10, mastery_after=20,
    )
    d = grade.to_dict()
    assert d["senseId"] == 42 and d["isCorrect"] is True
    assert d["masteryBefore"] == 10 and d["masteryAfter"] == 20


@pytest.mark.asyncio
async def test_realtime_token_includes_connection_expiry_and_public_sse_url(monkeypatch):
    uid = uuid.uuid4()
    monkeypatch.setattr(
        client, "mint_connection_token", lambda _user_id, _version: ("signed", 1234)
    )
    from pycil.realtime import router

    monkeypatch.setattr(router.settings, "centrifugo_public_sse_url", "https://api.test/connection/sse")

    result = await realtime_token(SimpleNamespace(id=uid, token_version=0))
    assert result.model_dump(by_alias=True) == {
        "token": "signed",
        "expiresAt": 1234,
        "sseUrl": "https://api.test/connection/sse",
    }


@pytest.mark.asyncio
async def test_disconnect_user_calls_centrifugo_and_handles_api_failures(monkeypatch):
    calls = []

    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return httpx.Response(200, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(client.httpx, "AsyncClient", lambda **_kwargs: MockAsyncClient())
    assert await client.disconnect_user("user-1") is True
    assert calls == [
        (
            f"{settings.centrifugo_url}/api/disconnect",
            {
                "json": {"user": "user-1"},
                "headers": {"X-API-Key": settings.centrifugo_api_key},
            },
        )
    ]

    class ErrorClient(MockAsyncClient):
        async def post(self, url, **kwargs):
            del kwargs
            return httpx.Response(
                200, json={"error": {"code": 100}}, request=httpx.Request("POST", url)
            )

    monkeypatch.setattr(client.httpx, "AsyncClient", lambda **_kwargs: ErrorClient())
    assert await client.disconnect_user("user-1") is False
