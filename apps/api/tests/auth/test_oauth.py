"""OIDC ID-token validation covers nonce and issuer checks."""

import pytest
from sqlalchemy import select

from pycil.auth import oauth
from pycil.auth.models import User
from pycil.auth.oauth import _validate_id_token
from pycil.config import settings


def _mock_verified_claims(monkeypatch, *, nonce: str, issuer: str = "https://accounts.google.com"):
    monkeypatch.setattr(oauth.jwt, "get_unverified_header", lambda _: {"alg": "RS256", "kid": "k"})
    monkeypatch.setattr(
        oauth.jwt,
        "decode",
        lambda *_args, **_kwargs: {
            "sub": "google-subject",
            "aud": settings.google_client_id,
            "iss": issuer,
            "nonce": nonce,
            "iat": 1,
            "exp": 2,
            "email": "verified@example.test",
            "email_verified": True,
        },
    )

    class Key:
        key_id = "k"
        key = object()

    class KeySet:
        keys = [Key()]

    monkeypatch.setattr(oauth.jwt.PyJWKSet, "from_dict", lambda _: KeySet())


def test_oidc_id_token_requires_matching_nonce(monkeypatch):
    _mock_verified_claims(monkeypatch, nonce="expected")
    claims = _validate_id_token("id-token", {"keys": []}, "expected")
    assert claims["email_verified"] is True

    with pytest.raises(ValueError, match="invalid_id_token_nonce"):
        _validate_id_token("id-token", {"keys": []}, "different")


def test_oidc_id_token_rejects_wrong_issuer(monkeypatch):
    _mock_verified_claims(monkeypatch, nonce="expected", issuer="https://attacker.example")
    with pytest.raises(ValueError, match="invalid_id_token_issuer"):
        _validate_id_token("id-token", {"keys": []}, "expected")


@pytest.mark.asyncio
async def test_callback_does_not_log_the_full_userinfo_payload(client, monkeypatch, caplog):
    """Privacy: the unverified-email branch logged the whole provider payload.

    `userinfo` carries email, name and picture URL. Logging it in full puts
    third-party personal data into application logs for a case that is not even an
    error worth that much detail — an unverified email is an expected outcome.
    """
    import logging

    from pycil.auth import router as auth_router

    payload = {
        "email": "unverified@example.com",
        "email_verified": False,
        "name": "Real Name",
        "picture": "https://example.com/private-photo.jpg",
    }

    async def exchange_code(_code, _state):
        return payload

    monkeypatch.setattr(auth_router.oauth, "exchange_code", exchange_code)
    with caplog.at_level(logging.INFO):
        response = await client.get("/v1/auth/callback?code=c&state=s")

    assert response.status_code == 401
    logged = " ".join(record.getMessage() for record in caplog.records)
    for secret in ("Real Name", "private-photo.jpg", "unverified@example.com"):
        assert secret not in logged, f"{secret!r} must not reach the logs"


@pytest.mark.asyncio
async def test_callback_does_not_leak_the_provider_exception_to_the_client(
    client, monkeypatch, caplog
):
    """The error code went out with the provider's exception text interpolated.

    `oauth_exchange_failed: {exc}` puts upstream detail — which can include URLs,
    tokens or internal hostnames — into a response body a browser receives. The log
    is the right place for it; the wire gets a stable code.
    """
    import logging

    from pycil.auth import router as auth_router

    async def exchange_code(_code, _state):
        raise RuntimeError("connect to https://internal-idp.corp:8443 failed: secret-token-abc")

    monkeypatch.setattr(auth_router.oauth, "exchange_code", exchange_code)
    with caplog.at_level(logging.ERROR):
        response = await client.get("/v1/auth/callback?code=c&state=s")

    assert response.status_code == 401
    body = response.text
    assert "secret-token-abc" not in body
    assert "internal-idp.corp" not in body
    # The diagnosis is kept, just not on the wire.
    assert "secret-token-abc" in " ".join(r.getMessage() for r in caplog.records) or any(
        r.exc_info for r in caplog.records
    )


@pytest.mark.asyncio
async def test_callback_rolls_back_user_when_refresh_issue_fails(client, session, monkeypatch):
    from pycil.auth import refresh_sessions
    from pycil.auth import router as auth_router

    async def exchange_code(_code, _state):
        return {
            "email": "oauth-rollback@example.test",
            "email_verified": True,
            "name": "OAuth Rollback",
        }

    async def fail_to_issue(*_args, **_kwargs):
        raise RuntimeError("refresh store unavailable")

    monkeypatch.setattr(auth_router.oauth, "exchange_code", exchange_code)
    monkeypatch.setattr(refresh_sessions, "issue", fail_to_issue)

    with pytest.raises(RuntimeError, match="refresh store unavailable"):
        await client.get("/v1/auth/callback?code=c&state=s")

    user = await session.scalar(select(User).where(User.email == "oauth-rollback@example.test"))
    assert user is None


def test_logout_uses_the_public_digest_helper_not_a_private_attribute():
    """`auth/router.py` reached into `refresh_sessions._digest`.

    A leading underscore is the module's own statement that the name is not part of
    its surface; two callers depending on it means the module cannot rename or
    change it. `account_lifecycle/service.py` does the same.
    """
    from pycil.auth import refresh_sessions

    assert hasattr(
        refresh_sessions, "token_digest"
    ), "the digest helper must have a public name its callers can use"
    assert refresh_sessions.token_digest("abc") == refresh_sessions._digest("abc")
