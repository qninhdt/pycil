"""Owned conversation metadata and native thread cleanup."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Protocol
from uuid import UUID

from anyio import CancelScope, sleep
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import DictRow
from psycopg_pool import AsyncConnectionPool
from redis.asyncio import Redis
from redis.asyncio.lock import Lock
from redis.exceptions import RedisError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.account.auth import ActorContext
from pycil.account.models import User
from pycil.app.http import Problem
from pycil.assistant.models import Conversation
from pycil.infrastructure.observability import get_logger

logger = get_logger(__name__)
LOCK_TTL_SECONDS = 30


class ConversationResources(Protocol):
    sessions: async_sessionmaker[AsyncSession]
    redis: Redis
    checkpoint_pool: AsyncConnectionPool[AsyncConnection[DictRow]]


async def owned(session: AsyncSession, user_id: UUID, identifier: UUID) -> Conversation:
    row = await session.scalar(
        select(Conversation).where(Conversation.id == identifier, Conversation.user_id == user_id)
    )
    if row is None:
        raise Problem(404, "conversation_not_found")
    return row


@asynccontextmanager
async def guard(redis: Redis, conversation_id: UUID) -> AsyncGenerator[None]:
    """A renewable native lease; no DB connection is held while work runs."""
    lock: Lock = redis.lock(
        f"pycil:conversation:{conversation_id}",
        timeout=LOCK_TTL_SECONDS,
        blocking=False,
        thread_local=False,
    )
    try:
        acquired = bool(await lock.acquire())
    except RedisError:
        raise Problem(503, "conversation_lock_unavailable") from None
    if not acquired:
        raise Problem(409, "conversation_busy")
    lost = False
    try:
        with CancelScope() as scope:

            async def renew() -> None:
                nonlocal lost
                while True:
                    await sleep(LOCK_TTL_SECONDS / 3)
                    try:
                        await lock.reacquire()
                    except RedisError:
                        logger.error(
                            "conversation_lease_renewal_failed",
                            conversation_id=str(conversation_id),
                        )
                        lost = True
                        scope.cancel()
                        return

            task = asyncio.create_task(renew())
            try:
                yield
            finally:
                task.cancel()
                with CancelScope(shield=True):
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
    finally:
        with CancelScope(shield=True):
            try:
                await lock.release()
            except RedisError as error:
                lost = True
                logger.error(
                    "conversation_lease_release_failed",
                    conversation_id=str(conversation_id),
                    error_type=type(error).__name__,
                )
    if lost:
        raise Problem(503, "conversation_lock_lost")


async def delete_conversation(
    resources: ConversationResources, user: User | ActorContext, identifier: UUID
) -> None:
    async with resources.sessions() as session:
        await owned(session, user.id, identifier)
    async with guard(resources.redis, identifier):
        async with resources.sessions() as session:
            await owned(session, user.id, identifier)
        await AsyncPostgresSaver(resources.checkpoint_pool).adelete_thread(str(identifier))
        async with resources.sessions() as session, session.begin():
            await session.execute(
                delete(Conversation).where(
                    Conversation.id == identifier, Conversation.user_id == user.id
                )
            )
        logger.info(
            "conversation_deleted",
            conversation_id=str(identifier),
            user_id=str(user.id),
        )
