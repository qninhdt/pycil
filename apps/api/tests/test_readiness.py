"""Readiness distinguishes mandatory dependencies from optional assistant state."""

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


class _Redis:
    def __init__(self, worker_ready: bool = True):
        self.worker_ready = worker_ready

    async def ping(self):
        return True

    async def get(self, _):
        return "1" if self.worker_ready else None


async def test_ready_requires_core_dependencies_but_not_optional_assistant(monkeypatch):
    monkeypatch.setattr(main, "engine", _Engine())
    monkeypatch.setattr(main, "get_redis", lambda: _Redis())
    monkeypatch.setattr(main, "centrifugo_readiness", lambda: _true())
    app = main.create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/health/live")).status_code == 200
        assert (await client.get("/health/ready")).status_code == 200
async def _true() -> bool:
    return True


async def test_ready_fails_without_worker_heartbeat(monkeypatch):
    monkeypatch.setattr(main, "engine", _Engine())
    monkeypatch.setattr(main, "get_redis", lambda: _Redis(worker_ready=False))
    monkeypatch.setattr(main, "centrifugo_readiness", _true)
    app = main.create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/health/ready")).status_code == 503


async def test_ready_fails_when_centrifugo_is_unavailable(monkeypatch):
    async def unavailable() -> bool:
        return False

    monkeypatch.setattr(main, "engine", _Engine())
    monkeypatch.setattr(main, "get_redis", lambda: _Redis())
    monkeypatch.setattr(main, "centrifugo_readiness", unavailable)
    app = main.create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "centrifugo_unavailable"
