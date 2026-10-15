"""The identity rename preserves populated user rows and their unique Clerk mapping."""

import asyncio

from alembic import command
from sqlalchemy import select, text

from pycil.account.models import User
from pycil.app.migrate import migration_config
from tests.support.account import account


async def test_identity_column_rename_preserves_existing_account(database):
    user, _ = await account(database.sessions)
    async with database.sessions() as session:
        original = (await session.execute(select(User.__table__).where(User.id == user.id))).one()
    # Recreate just this migration's input in the isolated test database.
    async with database.engine.begin() as connection:
        await connection.execute(text("ALTER TABLE users RENAME COLUMN clerk_id TO clerk_subject"))
        await connection.execute(
            text("ALTER TABLE users RENAME CONSTRAINT uq_users_clerk_id TO uq_users_clerk_subject")
        )
    config = migration_config(database.url)
    await asyncio.to_thread(command.stamp, config, "initial")
    await asyncio.to_thread(command.upgrade, config, "user_identity")
    async with database.sessions() as session:
        current = (await session.execute(select(User.__table__).where(User.id == user.id))).one()
        assert current == original
        names = set(
            await session.scalars(
                text("SELECT conname FROM pg_constraint WHERE conrelid='users'::regclass")
            )
        )
        assert "uq_users_clerk_id" in names and "uq_users_clerk_subject" not in names
