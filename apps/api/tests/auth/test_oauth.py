"""OIDC ID-token validation covers nonce and issuer checks."""

import pytest

from pycil.auth import oauth
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
