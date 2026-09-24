"""The frontend-facing API has one canonical `/v1` surface."""

import pytest
from httpx import ASGITransport, AsyncClient

from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.main import create_app

pytestmark = pytest.mark.asyncio


async def test_v1_me_capabilities_and_request_id():
    app = create_app()

    async def identity() -> CurrentUser:
        from uuid import uuid4

        return CurrentUser(id=uuid4(), email="learner@example.com")

    app.dependency_overrides[current_user] = identity
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        me = await client.get("/v1/me", headers={"X-Request-ID": "request-123"})
        capabilities = await client.get("/v1/capabilities")
        contract = await client.get("/v1/openapi.json")
        legacy = await client.get("/me")
        removed_auth = await client.get("/v1/auth/login")

    assert me.status_code == 200
    assert me.headers["X-Request-ID"] == "request-123"
    assert me.json()["email"] == "learner@example.com"
    assert capabilities.status_code == 200
    assert "realtime" not in capabilities.json()
    assert contract.status_code == 200
    assert "/v1/me" in contract.json()["paths"]
    assert legacy.status_code == 404
    assert legacy.json()["code"] == "not_found"
    assert legacy.json()["requestId"]
    # The custom login/refresh/logout routes are gone: Clerk signs users in and
    # issues sessions, so Pycil serves no auth endpoint of its own. An absent
    # route is the contract now, not a validation error from a live one.
    assert removed_auth.status_code == 404


async def test_next_question_openapi_has_a_render_format_discriminator_and_safe_payloads():
    schema = create_app().openapi()
    response = schema["paths"]["/v1/sessions/{session_id}/next"]["get"]["responses"]["200"]
    variants = response["content"]["application/json"]["schema"]["anyOf"][0]
    assert variants["discriminator"]["propertyName"] == "render_format"
    assert set(variants["discriminator"]["mapping"]) == {
        "flashcard",
        "single_choice",
        "text_span",
        "free_text",
    }
    rendered = str(schema["components"]["schemas"])
    assert "correct_index" not in rendered
    assert "accepted_forms" not in rendered
    assert "rubric" not in rendered
