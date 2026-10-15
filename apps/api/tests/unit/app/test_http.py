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
        assert response.headers["content-type"] == "application/problem+json"
        body_413 = response.json()
        assert body_413["code"] == "body_too_large"
        assert body_413["status"] == 413
        assert body_413["type"] == "about:blank"
        assert body_413["title"] == "Content Too Large"
        assert body_413["error"] == "body_too_large"
        assert response.headers["access-control-allow-origin"] == "https://web.example.test"
        assert response.headers["x-request-id"]
        response = await http.post("/echo", content=b"", headers={"Content-Length": "invalid"})
        assert response.status_code == 400
        assert response.headers["content-type"] == "application/problem+json"
        body_400 = response.json()
        assert body_400["code"] == "invalid_request"
        assert body_400["status"] == 400
        assert body_400["title"] == "Bad Request"
        assert body_400["error"] == "invalid_request"
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
        assert response.headers["content-type"] == "application/problem+json"
        data = response.json()
        assert data["code"] == "internal_error"
        assert data["status"] == 500
        assert data["type"] == "about:blank"
        assert data["title"] == "Internal Server Error"
        assert data["error"] == "internal_error"
        assert response.headers["x-request-id"] == request_id
        assert response.headers["access-control-allow-origin"] == "https://web.example.test"


async def test_rfc_9457_exception_handlers():
    from fastapi.exceptions import RequestValidationError
    from pydantic import BaseModel, Field
    from starlette.exceptions import HTTPException

    from pycil.app.http import (
        Problem,
        http_error_response,
        problem_response,
        validation_response,
    )

    test_app = FastAPI()
    test_app.add_exception_handler(Problem, problem_response)
    test_app.add_exception_handler(RequestValidationError, validation_response)
    test_app.add_exception_handler(HTTPException, http_error_response)

    class Payload(BaseModel):
        name: str = Field(min_length=3)

    @test_app.get("/problem")
    async def get_problem():
        raise Problem(404, "item_not_found", detail="Specific item detail")

    @test_app.post("/validate")
    async def post_validate(body: Payload):
        return {"name": body.name}

    @test_app.get("/http-error")
    async def get_http_error():
        raise HTTPException(405)

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="https://api.test") as client:
        # 1. Domain Problem
        res = await client.get("/problem")
        assert res.status_code == 404
        assert res.headers["content-type"] == "application/problem+json"
        p_data = res.json()
        assert p_data["type"] == "about:blank"
        assert p_data["title"] == "Not Found"
        assert p_data["status"] == 404
        assert p_data["code"] == "item_not_found"
        assert p_data["detail"] == "Specific item detail"
        assert p_data["instance"] == "/problem"
        assert p_data["error"] == "item_not_found"

        # 2. Validation error
        res_v = await client.post("/validate", json={"name": "x"})
        assert res_v.status_code == 422
        assert res_v.headers["content-type"] == "application/problem+json"
        v_data = res_v.json()
        assert v_data["code"] == "invalid_request"
        assert v_data["title"] == "Unprocessable Content"
        assert v_data["status"] == 422
        assert len(v_data["invalid_params"]) == 1
        assert v_data["invalid_params"][0]["name"] == "name"

        # 3. HTTPException
        res_h = await client.get("/http-error")
        assert res_h.status_code == 405
        assert res_h.headers["content-type"] == "application/problem+json"
        h_data = res_h.json()
        assert h_data["code"] == "method_not_allowed"
        assert h_data["status"] == 405
        assert h_data["title"] == "Method Not Allowed"
