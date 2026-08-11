"""The local bootstrap identity is explicit and impossible in production."""

import pytest
from sqlalchemy import select

from pycil.auth import refresh_sessions
from pycil.auth.dev_identity import assert_dev_identity_allowed, seed_and_issue_dev_token
from pycil.auth.models import RefreshSession, User
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
        (
            await session.execute(
                select(RefreshSession).where(RefreshSession.user_id == identity.user.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1, "the issued refresh token was not persisted"
    assert rows[0].revoked_at is None
    # The raw credential is never stored; only its digest is.
    assert identity.refresh_token not in str(rows[0].token_digest)


async def test_dev_identity_rolls_back_user_when_refresh_issue_fails(session, monkeypatch):
    async def fail_to_issue(*_args, **_kwargs):
        raise RuntimeError("refresh store unavailable")

    monkeypatch.setattr(refresh_sessions, "issue", fail_to_issue)

    with pytest.raises(RuntimeError, match="refresh store unavailable"):
        await seed_and_issue_dev_token(session, "rollback@test.local", _config())

    await session.rollback()
    user = await session.scalar(select(User).where(User.email == "rollback@test.local"))
    assert user is None


@pytest.mark.parametrize(
    "config",
    [_config(dev_identity_enabled=False), _config(environment="production")],
)
async def test_dev_identity_fails_closed(config):
    with pytest.raises(RuntimeError, match="dev identity is disabled"):
        assert_dev_identity_allowed(config)


@pytest.mark.parametrize("value", ["production ", " production", "\tprod\n", "PRODUCTION"])
async def test_dev_identity_is_refused_for_a_padded_production_name(value):
    """A trailing space must not re-enable the seed on a deployed instance.

    This command mints a bearer token for whatever email it is handed, with no
    credential of any kind. `ENVIRONMENT=production ` used to fall outside the
    refusal — one stray character in an env file or a copied CI secret, and the
    guard is off while every other production check reads as passing.
    """
    with pytest.raises(RuntimeError, match="dev identity is disabled"):
        assert_dev_identity_allowed(_config(environment=value))


@pytest.mark.parametrize("value", ["staging", "preview", "qa", "uat", "developmnet", ""])
async def test_dev_identity_is_refused_for_any_unrecognised_environment(value):
    """The guard is an allowlist: only named development environments may seed.

    This used to be the negation of the production check, so every name neither
    set mentioned got development's latitude. `ENVIRONMENT=staging` therefore
    minted a bearer token for any email supplied on the command line, with no
    credential — on a box that may hold real learners' data, and that answers
    "no" to the separate question of whether its secrets must be real.

    A typo is in this list on purpose. `developmnet` is the case a denylist
    handles worst: it reads as development to a human skimming an env file, and
    under the old rule it *was* treated as development, so the misspelling was
    invisible. Now it is refused, which is how the typo announces itself.
    """
    with pytest.raises(RuntimeError, match="dev identity is disabled"):
        assert_dev_identity_allowed(_config(environment=value))


@pytest.mark.parametrize("value", ["development", "dev", "local", "test", " DEV \n"])
async def test_dev_identity_still_works_for_the_named_development_environments(value):
    """The allowlist must not break the workflow it exists for.

    Tightening a guard until it refuses everything is not a fix, and the E2E suite
    authenticates through this command — so a name that legitimately means "local
    development" has to keep working, padding and case included.
    """
    assert_dev_identity_allowed(_config(environment=value))


async def test_the_flag_is_still_required_inside_a_development_environment():
    """Two independent conditions, so the allowlist is not the only thing standing.

    `DEV_IDENTITY_ENABLED` defaults to false. Even on a machine that passes the
    environment check, the seed stays off until someone opts in deliberately.
    """
    with pytest.raises(RuntimeError, match="dev identity is disabled"):
        assert_dev_identity_allowed(_config(dev_identity_enabled=False))
