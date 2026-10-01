"""Early middleware rejections retain the API's canonical error contract."""

import json
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from starlette.responses import StreamingResponse
from starlette.testclient import TestClient

from pycil.platform.errors import AppError, TooManyRequestsError, app_error_handler, error_responses
from pycil.platform.middleware import BodySizeLimitMiddleware, InternalSecretMiddleware


def test_body_limit_has_problem_details_security_headers_and_request_id():
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=2)

    @app.post("/payload")
    async def payload():
        return {"ok": True}

    response = TestClient(app).post("/payload", content="abc", headers={"X-Request-ID": "r-1"})
    assert response.status_code == 413
    assert response.json() == {
        "type": "about:blank",
        "title": "Content Too Large",
        "status": 413,
        "detail": "Body too large",
        "instance": "/payload",
        "code": "payload_too_large",
        "details": {},
        "requestId": "r-1",
    }
    assert response.headers["X-Request-ID"] == "r-1"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_internal_secret_rejection_has_problem_details(monkeypatch):
    from pycil.platform import middleware

    monkeypatch.setattr(middleware.settings, "internal_secret", "correct")
    app = FastAPI()
    app.add_middleware(InternalSecretMiddleware)

    @app.get("/internal/check")
    async def check():
        return {"ok": True}

    response = TestClient(app).get("/internal/check")
    assert response.status_code == 401
    assert response.json()["requestId"]
    assert response.headers["X-Frame-Options"] == "DENY"


def test_body_limit_does_not_turn_a_replayed_request_into_sse_disconnect():
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=10)

    async def chunks() -> AsyncIterator[bytes]:
        yield b"first\n"
        yield b"second\n"

    @app.post("/stream")
    async def stream():
        return StreamingResponse(chunks(), media_type="text/event-stream")

    response = TestClient(app).post("/stream", content="ok")
    assert response.status_code == 200
    assert response.text == "first\nsecond\n"


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
    assert json.loads(sent[1]["body"]) == {
        "type": "about:blank",
        "title": "Content Too Large",
        "status": 413,
        "detail": "Body too large",
        "instance": "/payload",
        "code": "payload_too_large",
        "details": {},
        "requestId": "chunked-r-1",
    }


def test_error_openapi_and_runtime_share_problem_details():
    app = FastAPI()
    app.add_exception_handler(AppError, app_error_handler)

    @app.get("/limited", responses=error_responses(429))
    async def limited():
        raise TooManyRequestsError(retry_after=30)

    response = TestClient(app).get("/limited")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert response.json() == {
        "type": "about:blank",
        "title": "Too Many Requests",
        "status": 429,
        "detail": "Too many requests",
        "instance": "/limited",
        "code": "too_many_requests",
        "details": {},
    }
    schema = app.openapi()
    problem_schema = schema["paths"]["/limited"]["get"]["responses"]["429"]["content"][
        "application/problem+json"
    ]["schema"]
    assert problem_schema["properties"]["code"]["type"] == "string"
