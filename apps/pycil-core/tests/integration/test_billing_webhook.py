"""Integration: Stripe webhook signature verification + out-of-order rejection.

`stripe.Webhook.construct_event` is monkeypatched per-test so the route's
signature path runs but never hits Stripe's network. Body is delivered as
raw bytes (the route reads `request.body()`).
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text


@pytest.fixture(autouse=True)
def _stripe_webhook_secret(monkeypatch):
    """Ensure the webhook handler is configured (else 503)."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_fake")
    # Force Settings cache miss so `stripe_webhook_secret` is picked up.
    from pycil_core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _patch_construct(monkeypatch, *, returns=None, raises=None):
    import stripe

    def fake(payload, sig, secret):
        if raises is not None:
            raise raises
        return returns

    monkeypatch.setattr(stripe.Webhook, "construct_event", fake)


async def test_bad_signature_returns_400(client, monkeypatch) -> None:
    import stripe

    _patch_construct(
        monkeypatch,
        raises=stripe.SignatureVerificationError("bad-sig", "sig", "body"),
    )
    response = await client.post(
        "/billing/webhook",
        content=b'{"x":1}',
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert response.status_code == 400


async def test_subscription_created_persists(
    client, session, test_user, monkeypatch
) -> None:
    """Happy path → 200, `subscriptions` row written for the user."""
    event = {
        "id": "evt_int_001",
        "type": "customer.subscription.created",
        "created": 1_000_000_000,
        "data": {"object": {
            "id": "sub_int_001",
            "metadata": {"user_id": str(test_user["id"])},
            "current_period_end": 1_000_000_999,
            "status": "active",
        }},
    }
    _patch_construct(monkeypatch, returns=event)

    response = await client.post(
        "/billing/webhook",
        content=json.dumps(event).encode(),
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert response.status_code == 200

    row = (
        await session.execute(
            text(
                "SELECT tier, last_event_id FROM subscriptions WHERE user_id = :u"
            ),
            {"u": test_user["id"]},
        )
    ).first()
    assert row is not None
    assert row.tier == "pro"
    assert row.last_event_id == "evt_int_001"


async def test_out_of_order_webhook_silently_no_op(
    client, session, test_user, monkeypatch
) -> None:
    """Older event after newer → 200, but DB row unchanged."""
    new_event = {
        "id": "evt_new",
        "type": "customer.subscription.updated",
        "created": 2_000_000_000,
        "data": {"object": {
            "id": "sub_x",
            "metadata": {"user_id": str(test_user["id"])},
            "current_period_end": 3_000_000_000,
            "status": "active",
        }},
    }
    old_event = {
        "id": "evt_old",
        "type": "customer.subscription.updated",
        "created": 1_500_000_000,  # older
        "data": {"object": {
            "id": "sub_x",
            "metadata": {"user_id": str(test_user["id"])},
            "current_period_end": 2_000_000_000,
            "status": "active",
        }},
    }

    _patch_construct(monkeypatch, returns=new_event)
    response = await client.post(
        "/billing/webhook",
        content=json.dumps(new_event).encode(),
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert response.status_code == 200

    _patch_construct(monkeypatch, returns=old_event)
    response2 = await client.post(
        "/billing/webhook",
        content=json.dumps(old_event).encode(),
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert response2.status_code == 200

    row = (
        await session.execute(
            text(
                "SELECT last_event_id FROM subscriptions WHERE user_id = :u"
            ),
            {"u": test_user["id"]},
        )
    ).first()
    # Newer event still wins; older was silently rejected.
    assert row.last_event_id == "evt_new"
