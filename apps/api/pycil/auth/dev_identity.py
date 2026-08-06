"""Explicit local-only identity seed/token command for frontend development."""

import argparse
import asyncio
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth import refresh_sessions, tokens
from pycil.auth.deps import get_user_by_email
from pycil.auth.models import User
from pycil.config import Settings, settings
from pycil.db.session import async_session_factory


def assert_dev_identity_allowed(config: Settings) -> None:
    """Refuse unless this is a named development environment and the flag is on.

    Both halves are required, and the environment half is an allowlist rather than
    "not production". Those are not the same test: this command seeds a user and
    issues it a full token pair for any email passed on the command line, so under
    a denylist `ENVIRONMENT=staging` — or a typo — was enough to become any learner
    on a box holding real data. The token is not a lesser one either; it is minted
    through `refresh_sessions.issue`, so it can refresh itself indefinitely.

    `DEV_IDENTITY_ENABLED` stays as the second half because it defaults to false:
    an environment being named `development` is not on its own a decision to allow
    this.
    """
    if not config.is_development or not config.dev_identity_enabled:
        raise RuntimeError("dev identity is disabled outside explicit development mode")


@dataclass(frozen=True)
class DevIdentity:
    """The same pair the OAuth callback seals, for a locally seeded identity."""

    user: User
    access_token: str
    expires_in: int
    refresh_token: str
    refresh_expires_in: int


async def seed_and_issue_dev_token(
    session: AsyncSession, email: str, config: Settings = settings
) -> DevIdentity:
    """Create/reuse one local identity and issue it a full token pair.

    The refresh half is not decoration. A session sealed without one is signed in
    and cannot do three things a real one can: refresh, sign out, or delete the
    account — all three take the refresh token, because all three revoke it. A
    fixture missing it therefore cannot reach those paths at all, and their specs
    fail on a "sign in again" notice that no real learner would ever see.

    Issued through `refresh_sessions.issue` rather than minted here, so the row it
    writes is the same one rotation and revocation operate on.
    """
    assert_dev_identity_allowed(config)
    user = await get_user_by_email(session, email)
    if user is None:
        user = User(email=email, name="Pycil Development")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    access_token, expires_in = tokens.sign_access(user)
    refresh_token, refresh_expires_in = await refresh_sessions.issue(session, user.id)
    await session.commit()
    return DevIdentity(
        user=user,
        access_token=access_token,
        expires_in=expires_in,
        refresh_token=refresh_token,
        refresh_expires_in=refresh_expires_in,
    )


async def _run(email: str) -> None:
    async with async_session_factory() as session:
        identity = await seed_and_issue_dev_token(session, email)
    print(f"email={identity.user.email}")
    print(f"access_token={identity.access_token}")
    print(f"expires_in={identity.expires_in}")
    print(f"refresh_token={identity.refresh_token}")
    print(f"refresh_expires_in={identity.refresh_expires_in}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed a local Pycil identity and print a bearer token"
    )
    parser.add_argument("--email", default=settings.dev_identity_email)
    args = parser.parse_args()
    assert_dev_identity_allowed(settings)
    asyncio.run(_run(args.email))


if __name__ == "__main__":
    main()
