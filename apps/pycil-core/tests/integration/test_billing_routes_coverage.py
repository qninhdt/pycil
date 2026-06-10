"""Billing HTTP API coverage: checkout config-gate + webhook branches.

Complements `test_billing_webhook.py` (signature + out-of-order). Here we
pin:
- /checkout 503 when Stripe unconfigured; happy path with Stripe SDK
  monkeypatched (no network) returns the session URL.
- /webhook 503 when webhook secret unset.
- /webhook duplicate event_id → {ok, duplicate} short-circuit (idempotency).
- /webhook subscription.updated + subscription.deleted dispatch branches.
- /webhook event with no user_id metadata → 200, no subscription row.

Stripe SDK calls are monkeypatched so nothing leaves the process.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text


# ---------------------------------------------------------------------------
# /billing/checkout
# ---------------------------------------------------------------------------

async def test_checkout_not_configured_503(client, monkeypatch) -> None:
    """No stripe_secret_key / price id → 503 billing_not_configured."""
    from pycil_core.config import get_settings

    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_PRICE_ID_PRO", raising=False)
    get_settings.cache_clear()
    try:
        resp = await client.post("/billing/checkout")
        assert resp.status_code == 503
        assert resp.json()["detail"] == "billing_not_configured"
    finally:
        get_settings.cache_clear()


async def test_checkout_happy_path_returns_url(
    client, session, test_user, monkeypatch
) -> None:
    """Configured + Stripe SDK stubbed → 200 with checkout URL."""
    from pycil_core.config import get_settings

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_PRICE_ID_PRO", "price_fake")
    get_settings.cache_clear()

    import stripe

    # Stub customer creation (billing_service.get_or_create_stripe_customer
    # calls stripe.Customer.create via asyncio.to_thread).
    class _Customer:
        id = "cus_fake_123"

    monkeypatch.setattr(
        stripe.Customer, "create", lambda **kw: _Customer()
    )

    class _Session:
        url = "https://checkout.stripe.test/session/abc"

    monkeypatch.setattr(
        stripe.checkout.Session, "create", lambda **kw: _Session()
    )

    try:
        resp = await client.post("/billing/checkout")
        assert resp.status_code == 200, resp.text
        assert resp.json()["url"] == "https://checkout.stripe.test/session/abc"

        # stripe_customer_id persisted on the user.
        row = (
            await session.execute(
                text("SELECT stripe_customer_id FROM users WHERE id = :u"),
                {"u": test_user["id"]},
            )
        ).first()
        assert row.stripe_customer_id == "cus_fake_123"
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# /billing/webhook config gate + dispatch branches
# ---------------------------------------------------------------------------

def _patch_construct(monkeypatch, *, returns):
    import stripe

    monkeypatch.setattr(
        stripe.Webhook, "construct_event", lambda payload, sig, secret: returns
    )


async def test_webhook_not_configured_503(client, monkeypatch) -> None:
    from pycil_core.config import get_settings

    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    get_settings.cache_clear()
    try:
        resp = await client.post(
            "/billing/webhook",
            content=b"{}",
            headers={"stripe-signature": "x"},
        )
        assert resp.status_code == 503
        assert resp.json()["detail"] == "webhook_not_configured"
    finally:
        get_settings.cache_clear()


@pytest.fixture
def _webhook_secret(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_fake")
    from pycil_core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_webhook_duplicate_short_circuits(
    client, session, test_user, monkeypatch, _webhook_secret
) -> None:
    """Same event_id twice → second returns duplicate, idempotent."""
    event = {
        "id": "evt_dup_001",
        "type": "customer.subscription.created",
        "created": 1_000_000_000,
        "data": {"object": {
            "id": "sub_dup",
            "metadata": {"user_id": str(test_user["id"])},
            "current_period_end": 1_000_000_999,
            "status": "active",
        }},
    }
    _patch_construct(monkeypatch, returns=event)

    body = json.dumps(event).encode()
    headers = {"stripe-signature": "t=1,v1=fake"}

    first = await client.post("/billing/webhook", content=body, headers=headers)
    assert first.status_code == 200
    assert first.json().get("duplicate") is not True

    second = await client.post("/billing/webhook", content=body, headers=headers)
    assert second.status_code == 200
    assert second.json()["duplicate"] is True


async def test_webhook_updated_branch_persists_status(
    client, session, test_user, monkeypatch, _webhook_secret
) -> None:
    """subscription.updated carries through obj.status into the row."""
    event = {
        "id": "evt_upd_001",
        "type": "customer.subscription.updated",
        "created": 1_500_000_000,
        "data": {"object": {
            "id": "sub_upd",
            "metadata": {"user_id": str(test_user["id"])},
            "current_period_end": 1_700_000_000,
            "status": "past_due",
        }},
    }
    _patch_construct(monkeypatch, returns=event)
    resp = await client.post(
        "/billing/webhook",
        content=json.dumps(event).encode(),
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert resp.status_code == 200

    row = (
        await session.execute(
            text("SELECT tier, status FROM subscriptions WHERE user_id = :u"),
            {"u": test_user["id"]},
        )
    ).first()
    assert row is not None
    assert row.tier == "pro"
    assert row.status == "past_due"


async def test_webhook_deleted_branch_downgrades_to_free(
    client, session, test_user, monkeypatch, _webhook_secret
) -> None:
    """subscription.deleted → tier=free, status=cancelled."""
    # First make an active pro subscription via a created event.
    created = {
        "id": "evt_del_setup",
        "type": "customer.subscription.created",
        "created": 1_000_000_000,
        "data": {"object": {
            "id": "sub_del",
            "metadata": {"user_id": str(test_user["id"])},
            "current_period_end": 1_900_000_000,
            "status": "active",
        }},
    }
    _patch_construct(monkeypatch, returns=created)
    await client.post(
        "/billing/webhook",
        content=json.dumps(created).encode(),
        headers={"stripe-signature": "t=1,v1=fake"},
    )

    deleted = {
        "id": "evt_del_001",
        "type": "customer.subscription.deleted",
        "created": 2_000_000_000,  # newer wins
        "data": {"object": {
            "id": "sub_del",
            "metadata": {"user_id": str(test_user["id"])},
            "status": "canceled",
        }},
    }
    _patch_construct(monkeypatch, returns=deleted)
    resp = await client.post(
        "/billing/webhook",
        content=json.dumps(deleted).encode(),
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert resp.status_code == 200

    row = (
        await session.execute(
            text("SELECT tier, status FROM subscriptions WHERE user_id = :u"),
            {"u": test_user["id"]},
        )
    ).first()
    assert row.tier == "free"
    assert row.status == "cancelled"


async def test_webhook_no_user_id_metadata_noop(
    client, session, monkeypatch, _webhook_secret
) -> None:
    """Event with no user_id in metadata → 200, no subscription written."""
    event = {
        "id": "evt_no_user",
        "type": "customer.subscription.created",
        "created": 1_000_000_000,
        "data": {"object": {
            "id": "sub_no_user",
            "metadata": {},
            "current_period_end": 1_000_000_999,
            "status": "active",
        }},
    }
    _patch_construct(monkeypatch, returns=event)
    resp = await client.post(
        "/billing/webhook",
        content=json.dumps(event).encode(),
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert resp.status_code == 200

    count = (
        await session.execute(text("SELECT COUNT(*) AS c FROM subscriptions"))
    ).first()
    assert count.c == 0
