"""Early middleware rejections retain the API's canonical error contract."""

import json

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from pycil.common.errors import AppError, TooManyRequestsError, app_error_handler, error_responses
from pycil.common.middleware import BodySizeLimitMiddleware, InternalSecretMiddleware


def test_body_limit_has_error_envelope_security_headers_and_request_id():
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=2)

    @app.post("/payload")
    async def payload():
        return {"ok": True}

    response = TestClient(app).post("/payload", content="abc", headers={"X-Request-ID": "r-1"})
    assert response.status_code == 413
    assert response.json()["error"] == {
        "code": "payload_too_large",
        "message": "Body too large",
        "details": {},
        "requestId": "r-1",
    }
    assert response.headers["X-Request-ID"] == "r-1"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_internal_secret_rejection_has_canonical_error_envelope(monkeypatch):
    from pycil.common import middleware

    monkeypatch.setattr(middleware.settings, "internal_secret", "correct")
    app = FastAPI()
    app.add_middleware(InternalSecretMiddleware)

    @app.get("/internal/check")
    async def check():
        return {"ok": True}

    response = TestClient(app).get("/internal/check")
    assert response.status_code == 401
    assert response.json()["error"]["requestId"]
    assert response.headers["X-Frame-Options"] == "DENY"


@pytest.mark.asyncio
async def test_chunked_body_over_limit_is_rejected_cumulatively():
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=2)

    @app.post("/payload")
    async def payload():
        return {"ok": True}

    incoming = iter(
        [
            {"type": "http.request", "body": b"ab", "more_body": True},
            {"type": "http.request", "body": b"c", "more_body": False},
        ]
    )
    sent = []

    async def receive():
        return next(incoming)

    async def send(message):
        sent.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "method": "POST",
            "scheme": "http",
            "path": "/payload",
            "raw_path": b"/payload",
            "query_string": b"",
            "headers": [(b"x-request-id", b"chunked-r-1")],
            "client": ("127.0.0.1", 123),
            "server": ("test", 80),
        },
        receive,
        send,
    )

    assert sent[0]["status"] == 413
    assert json.loads(sent[1]["body"])["error"] == {
        "code": "payload_too_large",
        "message": "Body too large",
        "details": {},
        "requestId": "chunked-r-1",
    }


def test_error_openapi_and_runtime_share_the_error_envelope():
    app = FastAPI()
    app.add_exception_handler(AppError, app_error_handler)

    @app.get("/limited", responses=error_responses(429))
    async def limited():
        raise TooManyRequestsError(retry_after=30)

    response = TestClient(app).get("/limited")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert response.json() == {
        "error": {
            "code": "too_many_requests",
            "message": "Too many requests",
            "details": {},
            "requestId": None,
        }
    }
    schema = app.openapi()
    assert schema["paths"]["/limited"]["get"]["responses"]["429"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/ErrorEnvelope"}
