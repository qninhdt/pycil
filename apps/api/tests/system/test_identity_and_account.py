"""SYS-A — Clerk subjects map to one internal UUID, and nothing else may.

The identity boundary is where a mistake is most expensive and least visible: two
accounts for one learner silently splits their library, and a merge hands one learner's
decks to another. Neither surfaces as an error, so both are pinned here through the real
verification path — the API process fetches JWKS over HTTP from a server this test
started, and every token below is genuinely signed.

What the journeys may not do: write to Redis or PostgreSQL *during* a flow. Seeding
before one is fine, and it is the only way to produce the pre-cutover row shape no
product path creates.
"""

import asyncio
import uuid

import jwt
import pytest

from tests.support.api_client import Api
from tests.system.conftest import requires_stack

pytestmark = [pytest.mark.asyncio, requires_stack]


async def test_concurrent_first_sign_ins_produce_one_account(actor, durable):
    """Two requests for a brand-new subject race; exactly one account may result.

    This is the ordinary case, not an exotic one: a browser issues several requests
    before the first finishes. If the claim is unguarded, both provision and the learner
    ends up with two libraries.
    """
    subject = f"user_{uuid.uuid4().hex[:16]}"
    caller = actor.token(subject)

    first, second = await asyncio.gather(caller.me(), caller.me())

    assert first["id"] == second["id"]
    rows = await durable.count("SELECT count(*) FROM users WHERE clerk_id = $1", subject)
    assert rows == 1, "a concurrent first sign-in created a second account"


async def test_a_verified_email_claims_an_unlinked_row_and_keeps_its_library(actor, durable):
    """A pre-cutover learner keeps their library when Clerk first sees them.

    The row exists with the email and no subject. Linking it is the whole point: the
    alternative is a fresh empty account beside the one holding their decks.
    """
    email = f"legacy-{uuid.uuid4().hex[:12]}@example.test"
    legacy_id = uuid.uuid4()
    await _insert_user(durable, legacy_id, email, subject=None)

    body = await actor.with_email(f"user_{uuid.uuid4().hex[:16]}", email).me()

    assert body["id"] == str(legacy_id), "the legacy row was not claimed"
    assert body["email"] == email


async def test_an_email_owned_by_another_subject_is_a_conflict_not_a_takeover(actor, durable):
    """Linking across two subjects would hand one learner's library to another."""
    email = f"taken-{uuid.uuid4().hex[:12]}@example.test"
    owner_subject = f"user_{uuid.uuid4().hex[:16]}"
    await _insert_user(durable, uuid.uuid4(), email, subject=owner_subject)

    response = await actor.with_email(f"user_{uuid.uuid4().hex[:16]}", email).get("/v1/me")

    assert response.status_code == 409
    assert response.json()["code"] == "identity_conflict"
    # And the owner is untouched: the row still belongs to the original subject.
    still = await durable.scalar(
        "SELECT clerk_id FROM users WHERE lower(email) = $1", email.lower()
    )
    assert still == owner_subject


async def test_an_unverified_email_does_not_claim_an_existing_account(actor, durable):
    """Only a *verified* claim may link. An unverified one is attacker-controlled."""
    email = f"unverified-{uuid.uuid4().hex[:12]}@example.test"
    victim_id = uuid.uuid4()
    await _insert_user(durable, victim_id, email, subject=None)

    caller = actor.with_email(f"user_{uuid.uuid4().hex[:16]}", email, email_verified=False)
    body = await caller.me()

    # A token without a verified claim provisions its own account rather than claiming
    # the row the email points at.
    assert body["id"] != str(victim_id)
    owner = await durable.scalar("SELECT clerk_id FROM users WHERE id = $1", victim_id)
    assert owner is None, "an unverified email claimed an existing account"


async def test_an_anonymous_public_read_is_allowed_and_a_private_one_is_not(actor):
    """A shared link is readable without an account; the library listing is not."""
    owner = actor.new()
    deck = await owner.deck("Public deck", visibility="PUBLIC")

    anonymous = actor.anonymous()

    assert (await anonymous.get(f"/v1/nodes/{deck['id']}")).status_code == 200
    assert (await anonymous.get("/v1/nodes")).status_code == 401


async def test_a_private_node_is_invisible_to_another_learner(actor):
    owner = actor.new()
    deck = await owner.deck("Private deck")

    stranger = actor.new()
    response = await stranger.get(f"/v1/nodes/{deck['id']}")

    assert response.status_code == 404
    assert response.json()["code"] == "node_not_found"


async def test_an_expired_token_is_refused_with_a_stable_code(actor, clerk_stub):
    """Expiry is checked, and the code is stable so a client can react to it."""
    expired = _reissue(clerk_stub, actor.raw_token(f"user_{uuid.uuid4().hex[:16]}"), {"exp": 1})

    response = await Api(actor.client, expired).get("/v1/me")

    assert response.status_code == 401
    assert response.json()["code"] == "expired_token"


async def test_a_token_from_another_issuer_is_refused(actor):
    """The issuer is pinned, so a token from a different Clerk instance fails."""
    from tests.support.clerk_jwks import ClerkStub

    other = ClerkStub()
    other.start()
    try:
        token = other.token(
            subject="user_other_issuer",
            email="other@example.test",
            issuer="https://clerk.somewhere-else.invalid",
        )
    finally:
        other.stop()

    response = await Api(actor.client, token).get("/v1/me")

    assert response.status_code == 401


# --- helpers ------------------------------------------------------------------


async def _insert_user(durable, user_id, email: str, *, subject: str | None) -> None:
    """Seed a row directly, because no product path creates an unlinked account.

    That shape is what the migration left behind, so a fixture is the only way to set
    the scenario up. This runs before the flow; nothing here writes during one.
    """
    await durable.connection.execute(
        "INSERT INTO users (id, email, clerk_id, created_at, updated_at) "
        "VALUES ($1, $2, $3, now(), now())",
        user_id,
        email,
        subject,
    )


def _reissue(clerk_stub, token: str, claims: dict) -> str:
    """Re-mint a token with altered claims, signed by the same key.

    Re-minting rather than hand-editing the payload: the signature must stay valid, or
    the test would pass because verification rejected a malformed token rather than
    because it rejected the claim.
    """
    decoded = jwt.decode(token, options={"verify_signature": False})
    decoded.update(claims)
    return jwt.encode(
        decoded, clerk_stub.private_key, algorithm="RS256", headers={"kid": clerk_stub.kid}
    )
