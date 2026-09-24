"""The credit projection a client reads for its allowance display.

Reported in Credits, never in currency, and clamped for display while the stored
balance stays signed — a turn admitted with a positive balance may finish and
drive it slightly negative, so the raw value is not what a client should render.
"""

from uuid import uuid4

import pytest

from pycil.account import credit
from pycil.account.plans import AccountPlan, period_grant
from pycil.auth.models import User
from tests.support.clerk_jwks import bearer

pytestmark = pytest.mark.asyncio


async def _signed_in(client, session, clerk_stub):
    user = User(email=f"credit-{uuid4()}@example.test", clerk_id=f"user_{uuid4().hex}")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    token = clerk_stub.token(subject=user.clerk_id, email=user.email)
    return user, bearer(token)


async def test_the_allowance_is_reported_in_credits_with_a_period(client, session, clerk_stub):
    _, headers = await _signed_in(client, session, clerk_stub)

    response = await client.get("/v1/me/credit", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "plan",
        "balance",
        "available",
        "period_start",
        "period_end",
        "period_used",
        "period_grant",
        "topup_balance",
    }
    assert body["plan"] == AccountPlan.free
    assert body["period_grant"] == period_grant(AccountPlan.free)
    assert body["available"] == body["balance"]
    assert body["period_start"] < body["period_end"]


async def test_an_overspent_balance_is_clamped_for_display_only(client, session, clerk_stub):
    """A negative balance is real; a negative *allowance* is not something to show.

    Overspend is recorded as usage beyond the grant, which is what an admitted turn
    that finished past the balance produces.
    """
    user, headers = await _signed_in(client, session, clerk_stub)
    row = await credit._ensure_credit(session, user.id)
    row.period_used = period_grant(AccountPlan.free) + 5_000
    await session.commit()

    body = (await client.get("/v1/me/credit", headers=headers)).json()

    assert body["balance"] == -5_000
    assert body["available"] == 0


async def test_the_payload_names_no_currency_or_price(client, session, clerk_stub):
    _, headers = await _signed_in(client, session, clerk_stub)

    import json

    serialized = json.dumps((await client.get("/v1/me/credit", headers=headers)).json())
    for forbidden in ("usd", "vnd", "price", "dollar", "$"):
        assert forbidden not in serialized.lower()


async def test_an_anonymous_caller_cannot_read_the_allowance(client):
    assert (await client.get("/v1/me/credit")).status_code == 401
