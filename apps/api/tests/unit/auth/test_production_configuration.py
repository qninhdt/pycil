"""Production startup configuration guards.

Clerk issues sessions, so the deploy-time secrets this must refuse are the Clerk
credentials plus the datastore and origin values. The old JWT/refresh/OAuth
requirements are gone with the custom auth stack.
"""

import pytest

from pycil.config import Settings, validate_production_settings


def _production_settings(**overrides) -> Settings:
    values = {
        "environment": "production",
        "domain": "api.example.com",
        "db_url": "postgresql+asyncpg://pycil:strong@postgres/pycil",
        "redis_url": "redis://:strong@redis:6379/0",
        "internal_secret": "b" * 40,
        "lexi_reference_dataset_fingerprint": "e" * 64,
        "allowed_origins": "https://app.example.com",
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
    placeholder secrets and a wildcard origin would both boot. Silence is the whole
    problem — nothing distinguishes "validated and safe" from "never ran".
    """
    with pytest.raises(RuntimeError, match="DB_URL"):
        validate_production_settings(_production_settings(environment=value, db_url=""))


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"allowed_origins": "*"}, "ALLOWED_ORIGINS"),
        ({"domain": "localhost"}, "DOMAIN"),
        ({"redis_url": "redis://:redis-dev-only@redis:6379/0"}, "REDIS_URL"),
        ({"redis_url": "redis://redis:6379/0"}, "REDIS_URL"),
        ({"db_url": "postgresql+asyncpg://pycil:changeme@postgres/pycil"}, "DB_URL"),
        ({"allowed_origins": "HTTP://app.example.com"}, "ALLOWED_ORIGINS"),
        ({"allowed_origins": "https://"}, "ALLOWED_ORIGINS"),
        ({"allowed_origins": "https://localhost:3000"}, "ALLOWED_ORIGINS"),
        ({"db_url": ""}, "DB_URL"),
        ({"redis_url": ""}, "REDIS_URL"),
        ({"internal_secret": ""}, "INTERNAL_SECRET"),
        ({"lexi_reference_dataset_fingerprint": ""}, "LEXI_REFERENCE_DATASET_FINGERPRINT"),
    ],
)
def test_production_configuration_rejects_unsafe_values(overrides, expected):
    with pytest.raises(RuntimeError, match=expected):
        validate_production_settings(_production_settings(**overrides))


def test_production_configuration_rejects_a_short_internal_secret():
    with pytest.raises(RuntimeError, match="INTERNAL_SECRET"):
        validate_production_settings(_production_settings(internal_secret="x"))
