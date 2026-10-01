"""Readiness checks stores the API actually needs, not an obsolete worker."""

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
    async def ping(self):
        return True


class _FailingRedis:
    async def ping(self):
        raise OSError("redis unavailable")


async def test_live_and_ready_pass_with_every_dependency_healthy(monkeypatch):
    monkeypatch.setattr(main, "engine", _Engine())
    monkeypatch.setattr(main, "get_redis", lambda: _Redis())
    app = main.create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/health/live")).status_code == 200
        assert (await client.get("/health/ready")).status_code == 200


async def test_ready_fails_without_redis(monkeypatch):
    monkeypatch.setattr(main, "engine", _Engine())
    monkeypatch.setattr(main, "get_redis", lambda: _FailingRedis())
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
