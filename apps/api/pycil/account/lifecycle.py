from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.models import User
from pycil.utils.errors import NotFound
from pycil.utils.orm import row_data


async def require_user(session: AsyncSession, user_id: UUID) -> User:
    """Check the account without serializing unrelated user writes."""
    user = await session.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update(read=True, key_share=True)
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise NotFound("account_not_found")
    return user


def invalidate_user_id(session: AsyncSession, clerk_id: str) -> None:
    if (store := session.info.get("user_id_store")) is not None:
        store.discard(clerk_id)


__all__ = ["invalidate_user_id", "require_user", "row_data"]
