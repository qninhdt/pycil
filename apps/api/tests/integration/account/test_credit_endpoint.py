"""The credit projection a client reads for its allowance display.

Reported in Credits, never in currency, and clamped for display while the stored
balance stays signed — a turn admitted with a positive balance may finish and
drive it slightly negative, so the raw value is not what a client should render.
"""

from uuid import uuid4

import pytest

from pycil.account.user import User
from pycil.billing.ledger import get_or_create_usage_period
from pycil.billing.plans import PlanKey, get_plan
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

    response = await client.get("/v1/me/credits", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "plan",
        "periodStart",
        "periodEnd",
        "allowanceUnits",
        "consumedUnits",
        "availableUnits",
    }
    assert body["plan"] == PlanKey.free
    assert body["allowanceUnits"] == get_plan(PlanKey.free).monthly_credit_units
    assert body["consumedUnits"] == 0
    assert body["availableUnits"] == body["allowanceUnits"]
    assert body["periodStart"] < body["periodEnd"]


async def test_an_overspent_balance_is_clamped_for_display_only(client, session, clerk_stub):
    """A negative balance is real; a negative *allowance* is not something to show.

    Overspend is recorded as usage beyond the grant, which is what an admitted turn
    that finished past the balance produces.
    """
    user, headers = await _signed_in(client, session, clerk_stub)
    period = await get_or_create_usage_period(session, user_id=user.id)
    period.used_units = get_plan(PlanKey.free).monthly_credit_units + 5_000
    await session.commit()

    body = (await client.get("/v1/me/credits", headers=headers)).json()

    assert body["consumedUnits"] == get_plan(PlanKey.free).monthly_credit_units + 5_000
    assert body["availableUnits"] == 0


async def test_the_payload_names_no_currency_or_price(client, session, clerk_stub):
    _, headers = await _signed_in(client, session, clerk_stub)

    import json

    serialized = json.dumps((await client.get("/v1/me/credits", headers=headers)).json())
    for forbidden in ("usd", "vnd", "price", "dollar", "$"):
        assert forbidden not in serialized.lower()


async def test_an_anonymous_caller_cannot_read_the_allowance(client):
    assert (await client.get("/v1/me/credits")).status_code == 401
