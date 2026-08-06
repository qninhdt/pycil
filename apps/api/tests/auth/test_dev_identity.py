"""The local bootstrap identity is explicit and impossible in production."""

import pytest
from sqlalchemy import select

from pycil.auth.dev_identity import assert_dev_identity_allowed, seed_and_issue_dev_token
from pycil.auth.models import RefreshSession
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
    first = await seed_and_issue_dev_token(session, "dev@test.local", config)
    second = await seed_and_issue_dev_token(session, "dev@test.local", config)
    assert first.user.id == second.user.id
    assert first.access_token
    assert first.expires_in > 0


async def test_dev_identity_issues_a_usable_refresh_token(session):
    """The pair is complete, and its refresh half is a real persisted session.

    Not completeness for its own sake. Refresh, sign-out and account deletion all
    take the refresh token, because all three revoke it — so an identity issued
    without one is signed in and cannot do any of them. The E2E fixture sealed
    exactly such a session, which silently put those three paths out of the
    suite's reach: the account-deletion spec failed on a "sign in again" notice
    that no real learner can see.

    The row is asserted, not just the string: a token minted here but never
    persisted would satisfy the caller and then be refused at first use.
    """
    identity = await seed_and_issue_dev_token(session, "pair@test.local", _config())

    assert identity.refresh_token
    assert identity.refresh_expires_in > 0
    # The access token is the short-lived half, which is what makes refreshing
    # meaningful at all.
    assert identity.refresh_expires_in > identity.expires_in

    rows = (
        await session.execute(
            select(RefreshSession).where(RefreshSession.user_id == identity.user.id)
        )
    ).scalars().all()
    assert len(rows) == 1, "the issued refresh token was not persisted"
    assert rows[0].revoked_at is None
    # The raw credential is never stored; only its digest is.
    assert identity.refresh_token not in str(rows[0].token_digest)


@pytest.mark.parametrize(
    "config",
    [_config(dev_identity_enabled=False), _config(environment="production")],
)
async def test_dev_identity_fails_closed(config):
    with pytest.raises(RuntimeError, match="dev identity is disabled"):
        assert_dev_identity_allowed(config)
