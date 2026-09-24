"""Resources every job handler receives, built once at worker startup."""

from asyncio import Task
from typing import TypedDict

from lexi_ai import Lexicon
from pycil.ports.lexi import LexiReader, LexiWorkerEngine
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


class WorkerContext(TypedDict, total=False):
    redis: Redis
    worker_id: str
    lexicon: Lexicon
    lexi_reader: LexiReader
    lexi_engine: LexiWorkerEngine
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    heartbeat_task: Task[None]


ReadyWorkerContext = WorkerContext
