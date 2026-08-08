"""Readiness distinguishes mandatory dependencies from optional assistant state."""

import pytest
from httpx import ASGITransport, AsyncClient

from pycil import main
from pycil.ports.centrifugo import get_centrifugo
from tests.realtime.fakes import FakeRealtimeControl

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


def _app_with(realtime: FakeRealtimeControl):
    """A real app whose broker is substituted at the dependency, not patched over.

    `/health/ready` takes `RealtimeControl` via `Depends` for exactly this reason:
    the readiness probe is the one caller that used to reach the module-level
    function directly, so `dependency_overrides` could not touch it and a test had
    to monkeypatch the module instead.
    """
    app = main.create_app()
    app.dependency_overrides[get_centrifugo] = lambda: realtime
    return app


async def test_ready_requires_core_dependencies_but_not_optional_assistant(monkeypatch):
    monkeypatch.setattr(main, "engine", _Engine())
    monkeypatch.setattr(main, "get_redis", lambda: _Redis())
    app = _app_with(FakeRealtimeControl())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/health/live")).status_code == 200
        assert (await client.get("/health/ready")).status_code == 200
async def test_ready_fails_without_worker_heartbeat(monkeypatch):
    monkeypatch.setattr(main, "engine", _Engine())
    monkeypatch.setattr(main, "get_redis", lambda: _Redis(worker_ready=False))
    app = _app_with(FakeRealtimeControl())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/health/ready")).status_code == 503


async def test_ready_fails_when_centrifugo_is_unavailable(monkeypatch):
    monkeypatch.setattr(main, "engine", _Engine())
    monkeypatch.setattr(main, "get_redis", lambda: _Redis())
    app = _app_with(FakeRealtimeControl(reachable=False))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "centrifugo_unavailable"
