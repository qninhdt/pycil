"""Typed runtime context shared by arq startup hooks and worker jobs."""

from asyncio import Lock
from collections.abc import Callable
from typing import Any, NotRequired, TypedDict

from lexi_ai import Lexicon
from pycil.ports.lexi import LexiReader, LexiWorkerEngine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


class WorkerContext(TypedDict, total=False):
    """Incrementally populated arq context used by lifecycle hooks.

    Startup is incremental and shutdown must tolerate partial initialization, so
    optional keys are intentional. The ready-state type below is what jobs consume.
    """

    redis: Any
    worker_id: str
    lexicon: Lexicon
    lexi_reader: LexiReader
    lexi_engine: LexiWorkerEngine
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    task_outbox_drain_lock: Lock
    task_outbox_listener: Any
    task_outbox_notification_callback: Callable[..., Any]


class ReadyWorkerContext(TypedDict):
    """Resources guaranteed to exist before a job is registered with arq."""

    redis: Any
    worker_id: str
    lexicon: Lexicon
    lexi_reader: LexiReader
    lexi_engine: LexiWorkerEngine
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    task_outbox_drain_lock: Lock
    task_outbox_listener: NotRequired[Any]
    task_outbox_notification_callback: NotRequired[Callable[..., Any]]
    job_try: NotRequired[int]
