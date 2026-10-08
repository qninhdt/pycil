import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import async_sessionmaker

from pycil.http import Problem
from pycil.main import create_app


class Input(BaseModel):
    count: int


@pytest.fixture
def app(config):
    application = create_app()
    application.state.product = config.model_copy(
        update={"http": config.http.model_copy(update={"max_body_bytes": 128})}
    )
    application.state.deployment = SimpleNamespace(allowed_origins=["https://client.invalid"])
    # An unbound native session suffices: missing auth must execute no database query.
    application.state.sessions = async_sessionmaker()

    @application.get("/domain-error")
    async def domain_error():
        raise Problem(403, "feature_not_available")

    @application.get("/unexpected")
    async def unexpected():
        raise RuntimeError("postgresql://secret-password@host/provider-secret")

    @application.post("/input")
    async def input_value(data: Input):
        return {"count": data.count}

    @application.post("/echo-length")
    async def length(request: Request):
        return {"bytes": len(await request.body())}

    @application.get("/stream")
    async def stream():
        async def chunks():
            yield b"first"
            yield b"second"

        return StreamingResponse(chunks())

    @application.get("/broken-stream")
    async def broken_stream():
        async def chunks():
            yield b"first"
            raise RuntimeError("sensitive-provider-stream-error")

        return StreamingResponse(chunks())

    return application


@pytest.mark.parametrize(
    "path, status, code",
    [
        ("/domain-error", 403, "feature_not_available"),
        ("/unexpected", 500, "internal_error"),
        ("/absent", 404, "not_found"),
        ("/v1/me", 401, "authentication_required"),
        ("/ready", 503, "not_ready"),
    ],
)
async def test_safe_error_codes_correlation_and_cors(app, caplog, path, status, code):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            path, headers={"Origin": "https://client.invalid", "X-Request-ID": "unsafe-id"}
        )
    assert response.status_code == status
    assert response.json() == {"error": code}
    assert UUID(response.headers["x-request-id"]).version == 7
    assert response.headers["access-control-allow-origin"] == "https://client.invalid"
    assert "secret-password" not in response.text + caplog.text
    assert "provider-secret" not in caplog.text
    assert not any(record.exc_info for record in caplog.records)


async def test_request_id_is_per_request_and_valid_uuid_can_be_propagated(app):
    key = str(uuid4())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.get("/health", headers={"X-Request-ID": key})
        second = await client.get("/health")
    assert first.headers["x-request-id"] == key
    assert second.headers["x-request-id"] != key
    assert UUID(second.headers["x-request-id"]).version == 7


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
async def test_validation_never_echoes_submitted_secret_and_blocks_wrong_origin(app, method):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/input",
            json={"count": "private-user-content"},
            headers={"Origin": "https://untrusted.invalid"},
        )
        malformed = await client.post(
            "/input", content=b'{"private-secret":', headers={"Content-Type": "application/json"}
        )
        preflight = await client.options(
            "/input",
            headers={
                "Origin": "https://client.invalid",
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": (
                    "Authorization,Content-Type,Idempotency-Key,X-Request-ID"
                ),
            },
        )
    assert response.status_code == malformed.status_code == 422
    assert response.json() == malformed.json() == {"error": "invalid_request"}
    assert "access-control-allow-origin" not in response.headers
    assert preflight.status_code == 200


@pytest.mark.parametrize("authorization", ["Basic secret", "Bearer", "Bearer ", "Bearer   "])
async def test_invalid_authorization_stays_401_even_on_optional_viewer_routes(app, authorization):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for path in ("/v1/me", "/v1/words:search?query=bank", "/v1/nodes"):
            response = await client.get(path, headers={"Authorization": authorization})
            assert response.status_code == 401
            assert response.json() == {"error": "invalid_credentials"}
            assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/v1/users:lookup?handle=learner"),
        ("GET", "/v1/words:search?query=bank"),
        ("GET", f"/v1/nodes/{uuid4()}:search?q=bank"),
        ("POST", "/v1/words:batchPreview"),
        ("POST", "/v1/me/senses:batchReadContext"),
        ("POST", f"/v1/nodes/{uuid4()}:modifySenses"),
        ("POST", f"/v1/nodes/{uuid4()}:move"),
        ("POST", f"/v1/nodes/{uuid4()}:copy"),
        ("POST", "/v1/study:prepare"),
        ("POST", "/v1/study:grade"),
        ("POST", "/v1/study:submitReviews"),
        ("POST", "/v1/study:batchSummarize"),
        ("POST", "/v1/assistant:run"),
    ],
)
async def test_custom_actions_dispatch_through_bearer_validation(app, method, path):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(method, path, headers={"Authorization": "Basic invalid"})
    assert response.status_code == 401
    assert response.json() == {"error": "invalid_credentials"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_openapi_has_typed_success_errors_optional_bearer_and_sse():
    schema = create_app().openapi()
    assert schema["components"]["securitySchemes"]["ClerkBearer"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    viewers = {
        ("get", "/v1/words:search"),
        ("get", "/v1/words/{word_id}"),
        ("get", "/v1/nodes"),
        ("get", "/v1/nodes/{node_id}"),
        ("get", "/v1/nodes/{node_id}/senses"),
        ("get", "/v1/users/{user_id}"),
        ("get", "/v1/users:lookup"),
        ("get", "/v1/discovery/nodes"),
        ("get", "/v1/nodes/{node_id}:search"),
        ("get", "/v1/nodes/{node_id}/senses/{sense_id}/sources"),
        ("post", "/v1/words:batchPreview"),
        ("post", "/v1/study:batchSummarize"),
    }
    count = 0
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            count += 1
            assert {"ClerkBearer": []} in operation["security"]
            assert ({} in operation["security"]) == ((method, path) in viewers)
            assert operation["responses"]["422"]["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/ErrorResponse"
            }
            for status, response in operation["responses"].items():
                if not status.startswith("2"):
                    continue
                if status == "204":
                    assert "content" not in response
                else:
                    for content in response["content"].values():
                        assert content["schema"]
    assert count == 41
    assert set(schema["paths"]["/v1/assistant:run"]["post"]["responses"]["200"]["content"]) == {
        "text/event-stream"
    }
    assert "HTTPValidationError" not in schema["components"]["schemas"]


@pytest.mark.parametrize("chunked", [False, True])
async def test_body_limit_counts_received_bytes_including_chunked_without_length(app, chunked):
    async def body():
        yield b"x" * 64
        yield b"y" * 65

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/echo-length",
            content=body() if chunked else b"x" * 129,
            headers={"Origin": "https://client.invalid"},
        )
        boundary = await client.post("/echo-length", content=b"x" * 128)
    assert response.status_code == 413
    assert response.json() == {"error": "body_too_large"}
    assert response.headers["access-control-allow-origin"] == "https://client.invalid"
    assert response.headers["x-request-id"]
    assert boundary.json() == {"bytes": 128}


async def test_invalid_content_length_is_safe(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/echo-length", content=b"abc", headers={"Content-Length": "-1"}
        )
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_request"}


async def test_stream_is_not_buffered_or_replaced_with_second_response(app, caplog):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/stream")).content == b"firstsecond"
        with pytest.raises(RuntimeError, match="Response interrupted") as caught:
            await client.get("/broken-stream")
    assert "sensitive-provider-stream-error" not in str(caught.value) + caplog.text


async def test_body_limit_handles_disconnect_without_calling_endpoint(app):
    sent = []

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    await app(
        {
            "type": "http",
            "http_version": "1.1",
            "scheme": "http",
            "method": "POST",
            "path": "/echo-length",
            "query_string": b"",
            "headers": [],
        },
        receive,
        send,
    )
    assert sent == []


def test_exported_openapi_matches_without_startup_or_obsolete_contracts():
    schema = create_app().openapi()
    exported = Path(__file__).resolve().parents[4] / "docs/backend/openapi.json"
    assert json.loads(exported.read_text()) == schema
    assert "/v1/study/history" not in schema["paths"]
    obsolete = {
        "question_budget",
        "mastery",
        "mastery_after",
        "weakest",
        "after_id",
        "after_updated_at",
        "next_after",
        "next_after_id",
    }
    for component in schema["components"]["schemas"].values():
        assert not obsolete.intersection(component.get("properties", {}))
