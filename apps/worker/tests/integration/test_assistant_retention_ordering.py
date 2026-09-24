"""Retention must delete checkpoints before committing thread removal.

Ordering is the contract: the LangGraph checkpoint rows are owned by the
checkpointer, not by SQLModel metadata, so the thread row is removed only after
the checkpointer has purged its own data. Committing the thread first would
orphan the checkpoints with no thread left to name them.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from pycil_worker.jobs import reconcile_assistant_retention as retention

pytestmark = pytest.mark.asyncio


def _connect():
    """Match the production shape: `connect(...)` is awaited, then used as a CM."""

    async def connect(*args, **kwargs):
        return _AsyncCtx()

    return connect


class _AsyncCtx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return None


class _Thread:
    def __init__(self, owner_id, thread_id):
        self.id = thread_id
        self.owner_id = owner_id
        self.retention_deadline = datetime(2020, 1, 1, tzinfo=UTC)


def _ctx(threads, order, *, session=None):
    session = session or AsyncMock()

    async def scalars(_statement):
        return list(threads)

    session.scalars = scalars
    session.delete = AsyncMock(side_effect=lambda thread: order.append("delete_thread_row"))
    session.commit = AsyncMock(side_effect=lambda: order.append("commit"))

    @asynccontextmanager
    async def session_factory():
        yield session

    return {"session_factory": session_factory}


async def test_checkpoint_delete_precedes_the_thread_row(monkeypatch):
    order: list[str] = []
    thread = _Thread(uuid4(), uuid4())
    ctx = _ctx([thread], order)

    class _Checkpointer:
        def __init__(self, connection):
            pass

        async def adelete_thread(self, key):
            order.append("delete_checkpoint")

    monkeypatch.setattr(retention, "AsyncPostgresSaver", _Checkpointer)
    monkeypatch.setattr(retention.AsyncConnection, "connect", _connect())

    purged = await retention.reconcile_assistant_retention(ctx)

    assert purged == 1
    assert order == ["delete_checkpoint", "delete_thread_row", "commit"], (
        "the checkpointer must purge before the thread row is removed"
    )


async def test_no_expired_threads_opens_no_checkpointer(monkeypatch):
    """An empty sweep must not connect to the checkpoint database at all."""
    order: list[str] = []
    ctx = _ctx([], order)
    connected = False

    async def _connect(*args, **kwargs):
        nonlocal connected
        connected = True
        return _AsyncCtx()

    monkeypatch.setattr(retention.AsyncConnection, "connect", _connect)

    assert await retention.reconcile_assistant_retention(ctx) == 0
    assert not connected


async def test_the_sweep_selects_by_deadline_without_a_run_table():
    """The sweep is bounded by the retention deadline alone.

    Asserted on the compiled statement rather than on data: the predicate lives in
    the SQL, and a rewrite that reached for the dropped run table would fail at
    runtime instead of deleting the right rows.
    """
    ctx = _ctx([], [])
    captured = {}

    async def scalars(statement):
        captured["sql"] = str(statement)
        return []

    ctx["session_factory"].__wrapped__ = None  # noqa: B010 - clarity only
    session = SimpleNamespace(scalars=scalars, delete=AsyncMock(), commit=AsyncMock())

    @asynccontextmanager
    async def factory():
        yield session

    await retention.reconcile_assistant_retention({"session_factory": factory})

    sql = captured["sql"].lower()
    assert "retention_deadline" in sql
    # An in-flight turn is bounded by the Redis lease, not a run row, so the sweep
    # must not depend on a table the schema no longer has.
    assert "assistant_runs" not in sql
