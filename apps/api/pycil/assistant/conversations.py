"""Owned conversation metadata and native thread cleanup."""

import asyncio
from contextlib import asynccontextmanager

from anyio import CancelScope, sleep
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.exceptions import RedisError
from sqlalchemy import delete, select

from pycil.assistant.models import Conversation
from pycil.http import Problem
from pycil.logging import get_logger

logger = get_logger(__name__)
LOCK_TTL_SECONDS = 30


async def owned(session, user_id, identifier):
    row = await session.scalar(
        select(Conversation).where(Conversation.id == identifier, Conversation.user_id == user_id)
    )
    if row is None:
        raise Problem(404, "conversation_not_found")
    return row


@asynccontextmanager
async def guard(redis, conversation_id):
    """A renewable native lease; no DB connection is held while work runs."""
    lock = redis.lock(
        f"pycil:conversation:{conversation_id}",
        timeout=LOCK_TTL_SECONDS,
        blocking=False,
        thread_local=False,
    )
    try:
        acquired = await lock.acquire()
    except RedisError:
        raise Problem(503, "conversation_lock_unavailable") from None
    if not acquired:
        raise Problem(409, "conversation_busy")
    lost = False
    try:
        with CancelScope() as scope:

            async def renew():
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
            except RedisError:
                lost = True
                logger.exception(
                    "conversation_lease_release_failed",
                    conversation_id=str(conversation_id),
                )
    if lost:
        raise Problem(503, "conversation_lock_lost")


async def delete_conversation(resources, user, identifier):
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
