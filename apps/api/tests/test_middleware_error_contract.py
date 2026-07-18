"""Early middleware rejections retain the API's canonical error contract."""

from fastapi import FastAPI
from starlette.testclient import TestClient

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
