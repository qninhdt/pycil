"""Fail-closed prod-secret enforcement on Settings.

Pinned:
- app_env != prod: optional secrets may be unset (dev/test boot freely).
- app_env == prod with all required secrets: constructs fine.
- app_env == prod missing OpenRouter / S3 secrets: rejected, and the error
  names every missing var so an operator can fix the deploy in one pass.
- app_env normalizes case/whitespace ("  PROD " → "prod").
"""
from __future__ import annotations

import pytest

from pycil_core.config import Settings

# The ambient shell / .env may set these; clear them so each test controls the
# full secret surface and pydantic does not read a leaked value from the env.
_CLEARED_ENV = (
    "OPENROUTER_API_KEY",
    "OPENROUTER_MODEL",
    "OPENROUTER_CHAT_MODEL",
    "S3_BUCKET",
    "S3_ENDPOINT",
    "S3_KEY_ID",
    "S3_APPLICATION_KEY",
    "APP_ENV",
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _CLEARED_ENV:
        monkeypatch.delenv(var, raising=False)


_BASE = {
    "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
    "REDIS_URL": "redis://localhost:6379/0",
    "AUTH_JWT_SECRET": "x" * 32,
    "INTERNAL_API_SECRET": "y" * 32,
}

_PROD_SECRETS = {
    "OPENROUTER_API_KEY": "sk-test",
    "S3_BUCKET": "pycil",
    "S3_APPLICATION_KEY": "s3secret",
}


def _settings(**overrides) -> Settings:
    return Settings(**{**_BASE, **overrides})  # type: ignore[arg-type]


def test_dev_boots_without_optional_secrets() -> None:
    s = _settings(APP_ENV="dev")._require_prod_secrets()
    assert s.app_env == "dev"
    assert s.openrouter_api_key is None


def test_prod_with_all_secrets_boots() -> None:
    s = _settings(APP_ENV="prod", **_PROD_SECRETS)._require_prod_secrets()
    assert s.app_env == "prod"


def test_prod_missing_secrets_rejected_and_names_them() -> None:
    with pytest.raises(ValueError) as exc:
        _settings(APP_ENV="prod")._require_prod_secrets()
    msg = str(exc.value)
    assert "OPENROUTER_API_KEY" in msg
    assert "S3_BUCKET" in msg
    assert "S3_APPLICATION_KEY" in msg


def test_app_env_normalizes_case_and_whitespace() -> None:
    s = _settings(APP_ENV="  PROD ", **_PROD_SECRETS)
    assert s.app_env == "prod"
