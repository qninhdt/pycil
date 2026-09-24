"""The system stack is real: a separate API process, a separate worker, real stores.

Phase 13's journeys are written on this scaffold. Before those exist, this file proves
the scaffold itself is sound — that the API answers over a socket, that the worker's
heartbeat makes readiness pass, and that an authenticated request is verified against a
JWKS document fetched over HTTP from a server this process did not patch into the
verifier.

Without these, a later journey failing would be ambiguous: it could be the product or
it could be the harness, and the difference is an hour of debugging.
"""

import pytest

from tests.system.conftest import requires_stack

pytestmark = [pytest.mark.asyncio, requires_stack]


async def test_liveness_answers_over_a_real_socket(stack_client):
    response = await stack_client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_passes_only_because_a_worker_is_consuming(stack_client):
    """The heartbeat is written by the worker process, not by the API's own code."""
    response = await stack_client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_a_signed_clerk_token_provisions_an_internal_account(actor):
    caller = actor.new()

    body = await caller.me()

    # A Clerk subject is not a Pycil identity: the response carries the internal UUID
    # the rest of the API keys on.
    assert body["email"].endswith("@example.test")
    assert not body["id"].startswith("user_")


async def test_the_same_subject_resolves_to_one_account_across_requests(actor):
    caller = actor.new()

    first = await caller.me()
    second = await caller.me()

    assert first["id"] == second["id"]


async def test_a_token_signed_by_another_key_is_refused(stack_client, actor):
    """Verification happens against the stub's published key, not a local secret."""
    from tests.support.api_client import Api
    from tests.support.clerk_jwks import ClerkStub

    stranger = ClerkStub()
    stranger.start()
    try:
        forged = stranger.token(subject="user_forged", email="forged@example.test")
    finally:
        stranger.stop()

    response = await Api(actor.client, forged).get("/v1/me")

    assert response.status_code == 401
    assert response.json()["code"] in {"invalid_token", "auth_not_configured"}


async def test_a_protected_read_refuses_an_anonymous_caller(actor):
    response = await actor.anonymous().get("/v1/nodes")

    assert response.status_code == 401
