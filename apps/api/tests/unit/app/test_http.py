from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from pycil.app.http import BodyLimit, RequestBoundary, RuntimeCORS


def boundary_app():
    app = FastAPI()
    app.state.config = SimpleNamespace(
        runtime=SimpleNamespace(http=SimpleNamespace(max_body_bytes=6))
    )
    app.state.deployment = SimpleNamespace(allowed_origins=["https://web.example.test"])
    app.add_middleware(BodyLimit)
    app.add_middleware(RequestBoundary)
    app.add_middleware(RuntimeCORS)
    return app


async def test_streamed_body_limit_prevents_dispatch_even_with_a_false_length():
    app = boundary_app()
    received = []

    @app.post("/echo")
    async def echo(request: Request):
        body = await request.body()
        received.append(body)
        return {"size": len(body)}

    async def chunks(*parts):
        for part in parts:
            yield part

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://api.test") as http:
        response = await http.post("/echo", content=chunks(b"abc", b"def"))
        assert response.json() == {"size": 6}
        response = await http.post(
            "/echo",
            content=chunks(b"abc", b"defg"),
            headers={"Content-Length": "0", "Origin": "https://web.example.test"},
        )
        assert response.status_code == 413
        assert response.json() == {"error": "body_too_large"}
        assert response.headers["access-control-allow-origin"] == "https://web.example.test"
        assert response.headers["x-request-id"]
        response = await http.post("/echo", content=b"", headers={"Content-Length": "invalid"})
        assert response.status_code == 400
        assert response.json() == {"error": "invalid_request"}
        assert received == [b"abcdef"]


async def test_unhandled_error_is_redacted_and_retains_request_correlation():
    app = boundary_app()

    @app.get("/failure")
    async def failure():
        raise RuntimeError("private-provider-token-and-learner-content")

    request_id = str(uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://api.test") as http:
        response = await http.get(
            "/failure",
            headers={"X-Request-ID": request_id, "Origin": "https://web.example.test"},
        )
        assert response.status_code == 500
        assert response.json() == {"error": "internal_error"}
        assert response.headers["x-request-id"] == request_id
        assert response.headers["access-control-allow-origin"] == "https://web.example.test"
