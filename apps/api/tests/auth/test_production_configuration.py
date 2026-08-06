"""Production startup configuration and OAuth redirect allowlist tests."""

import pytest

from pycil.auth import oauth
from pycil.config import Settings, validate_production_settings


def _production_settings(**overrides) -> Settings:
    values = {
        "environment": "production",
        "domain": "api.example.com",
        "db_url": "postgresql+asyncpg://pycil:strong@postgres/pycil",
        "jwt_secret": "a" * 40,
        "refresh_token_pepper": "r" * 40,
        "internal_secret": "b" * 40,
        "centrifugo_api_key": "c" * 40,
        "centrifugo_token_hmac_secret": "d" * 40,
        "centrifugo_subscribe_proxy_secret": "s" * 40,
        "lexi_reference_dataset_fingerprint": "e" * 64,
        "google_client_id": "client-id.apps.googleusercontent.com",
        "google_client_secret": "google-secret",
        "allowed_origins": "https://app.example.com",
        "oauth_redirect_uris": "https://app.example.com/api/auth/callback",
        "centrifugo_public_sse_url": "https://api.example.com/connection/sse",
    }
    values.update(overrides)
    return Settings(**values)


def test_production_configuration_accepts_exact_values():
    validate_production_settings(_production_settings())


@pytest.mark.parametrize("value", ["production ", " production", "\tprod\n", "Production"])
def test_a_padded_environment_name_is_still_production(value):
    """Whitespace around the value must not switch the deploy guard off.

    `ENVIRONMENT=production ` is one trailing space in an env file or a copied CI
    secret, and it used to make this function return before checking anything:
    placeholder secrets, a wildcard origin and an empty OAuth allowlist would all
    boot. Silence is the whole problem — nothing distinguishes "validated and
    safe" from "never ran".
    """
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        validate_production_settings(
            _production_settings(environment=value, jwt_secret="changeme")
        )


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"jwt_secret": "changeme"}, "JWT_SECRET"),
        ({"allowed_origins": "*"}, "ALLOWED_ORIGINS"),
        ({"oauth_redirect_uris": ""}, "OAUTH_REDIRECT_URIS"),
        ({"domain": "localhost"}, "DOMAIN"),
    ],
)
def test_production_configuration_rejects_unsafe_values(overrides, expected):
    with pytest.raises(RuntimeError, match=expected):
        validate_production_settings(_production_settings(**overrides))


async def test_oauth_login_rejects_redirect_outside_configured_allowlist(monkeypatch):
    monkeypatch.setattr(
        oauth.settings,
        "oauth_redirect_uris",
        "https://app.example.com/api/auth/callback",
    )
    with pytest.raises(ValueError, match="redirect_uri_not_allowed"):
        await oauth.build_authorize_url("https://attacker.example/callback")
