"""Explicit local-only identity seed/token command for frontend development."""

import argparse
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth import tokens
from pycil.auth.deps import get_user_by_email
from pycil.auth.models import User
from pycil.config import Settings, settings
from pycil.db.session import async_session_factory


def assert_dev_identity_allowed(config: Settings) -> None:
    if config.environment.lower() in {"production", "prod"} or not config.dev_identity_enabled:
        raise RuntimeError("dev identity is disabled outside explicit development mode")


async def seed_and_issue_dev_token(
    session: AsyncSession, email: str, config: Settings = settings
) -> tuple[User, str, int]:
    """Create/reuse one local identity and return a normal Pycil bearer token."""
    assert_dev_identity_allowed(config)
    user = await get_user_by_email(session, email)
    if user is None:
        user = User(email=email, name="Pycil Development")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    token, ttl = tokens.sign_access(user)
    return user, token, ttl


async def _run(email: str) -> None:
    async with async_session_factory() as session:
        user, token, ttl = await seed_and_issue_dev_token(session, email)
    print(f"email={user.email}")
    print(f"access_token={token}")
    print(f"expires_in={ttl}")


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
