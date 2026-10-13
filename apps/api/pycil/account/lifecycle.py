"""Identity verification and short-lived account existence checks."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.models import User
from pycil.app.http import Problem


def row_data(row: Any) -> dict[str, Any]:
    return {
        str(column.name): getattr(row, column.name)
        for column in row.__table__.columns
        if column.computed is None
    }


async def require_user(session: AsyncSession, user_id: UUID) -> User:
    """Check the account without serializing unrelated user writes."""
    user = await session.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update(read=True, key_share=True)
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise Problem(404, "account_not_found")
    return user


async def invalidate_actor(session: AsyncSession, user: User) -> None:
    if cache := session.info.get("cache"):
        await cache.discard(f"actor:v3:{user.clerk_subject}")
