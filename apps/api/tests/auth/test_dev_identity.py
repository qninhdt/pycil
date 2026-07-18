"""The local bootstrap identity is explicit and impossible in production."""

import pytest

from pycil.auth.dev_identity import assert_dev_identity_allowed, seed_and_issue_dev_token
from pycil.config import Settings

pytestmark = pytest.mark.asyncio


def _config(**overrides) -> Settings:
    values = {
        "environment": "development",
        "dev_identity_enabled": True,
        "jwt_secret": "a" * 40,
    }
    values.update(overrides)
    return Settings(**values)


async def test_dev_identity_seeds_once_and_issues_a_normal_token(session):
    config = _config()
    first, token, ttl = await seed_and_issue_dev_token(session, "dev@test.local", config)
    second, _, _ = await seed_and_issue_dev_token(session, "dev@test.local", config)
    assert first.id == second.id
    assert token
    assert ttl > 0


@pytest.mark.parametrize(
    "config",
    [_config(dev_identity_enabled=False), _config(environment="production")],
)
async def test_dev_identity_fails_closed(config):
    with pytest.raises(RuntimeError, match="dev identity is disabled"):
        assert_dev_identity_allowed(config)
