"""Internal-secret middleware: constant-time guard on /internal/* routes."""

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from pycil.common.middleware import InternalSecretMiddleware


@pytest.fixture
def client(monkeypatch):
    from pycil.common import middleware

    monkeypatch.setattr(middleware.settings, "internal_secret", "correct-secret")
    app = FastAPI()
    app.add_middleware(InternalSecretMiddleware)

    @app.get("/internal/ping")
    async def ping():
        return {"ok": True}

    @app.get("/public")
    async def public():
        return {"ok": True}

    return TestClient(app)


def test_public_route_bypasses_guard(client):
    assert client.get("/public").status_code == 200


def test_correct_secret_allowed(client):
    resp = client.get("/internal/ping", headers={"X-Internal-Secret": "correct-secret"})
    assert resp.status_code == 200


def test_missing_header_rejected(client):
    assert client.get("/internal/ping").status_code == 401


def test_empty_header_rejected(client):
    resp = client.get("/internal/ping", headers={"X-Internal-Secret": ""})
    assert resp.status_code == 401


def test_wrong_secret_rejected(client):
    resp = client.get("/internal/ping", headers={"X-Internal-Secret": "wrong"})
    assert resp.status_code == 401


def test_empty_configured_secret_fails_closed(monkeypatch):
    from pycil.common import middleware

    monkeypatch.setattr(middleware.settings, "internal_secret", "")
    app = FastAPI()
    app.add_middleware(InternalSecretMiddleware)

    @app.get("/internal/ping")
    async def ping():
        return {"ok": True}

    c = TestClient(app)
    # Even a matching-looking empty header must be rejected when unset.
    assert c.get("/internal/ping", headers={"X-Internal-Secret": ""}).status_code == 401
