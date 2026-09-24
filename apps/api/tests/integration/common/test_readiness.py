"""Readiness fails on a stale worker heartbeat, not only on an unreachable database.

A healthy database is not a ready service: jobs are written by the API and consumed
by the worker, so a stale heartbeat means committed work has nobody to perform it.
The gateway reachability check that used to live here went with the gateway itself.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from pycil import main

pytestmark = pytest.mark.asyncio


class _Connection:
    async def execute(self, _):
        return None


class _ConnectionContext:
    async def __aenter__(self):
        return _Connection()

    async def __aexit__(self, *_):
        return None


class _Engine:
    def connect(self):
        return _ConnectionContext()


class _FailingEngine:
    def connect(self):
        raise OSError("connection refused")


class _Redis:
    def __init__(self, worker_ready: bool = True):
        self.worker_ready = worker_ready

    async def ping(self):
        return True

    async def get(self, _):
        return "1" if self.worker_ready else None


async def test_live_and_ready_pass_with_every_dependency_healthy(monkeypatch):
    monkeypatch.setattr(main, "engine", _Engine())
    monkeypatch.setattr(main, "get_redis", lambda: _Redis())
    app = main.create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/health/live")).status_code == 200
        assert (await client.get("/health/ready")).status_code == 200


async def test_ready_fails_without_worker_heartbeat(monkeypatch):
    monkeypatch.setattr(main, "engine", _Engine())
    monkeypatch.setattr(main, "get_redis", lambda: _Redis(worker_ready=False))
    app = main.create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/health/ready")).status_code == 503


async def test_live_stays_up_when_a_dependency_is_down(monkeypatch):
    """Liveness must not restart a container over a dependency it cannot fix."""
    monkeypatch.setattr(main, "engine", _FailingEngine())
    monkeypatch.setattr(main, "get_redis", lambda: _Redis())
    app = main.create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/health/live")).status_code == 200
        assert (await client.get("/health/ready")).status_code == 503
