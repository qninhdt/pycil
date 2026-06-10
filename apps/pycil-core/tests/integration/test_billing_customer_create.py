"""`billing_service.get_or_create_stripe_customer` — Stripe SDK mocked."""
from __future__ import annotations

from sqlalchemy import text

from pycil_core.services import billing_service


async def test_existing_customer_skips_sdk_call(session, test_user, monkeypatch) -> None:
    """When `users.stripe_customer_id` is set, do NOT call Stripe."""
    sdk_calls: list[dict] = []

    def fake_create(**kwargs):
        sdk_calls.append(kwargs)
        return type("Customer", (), {"id": "cus_should_not_be_used"})()

    import stripe
    monkeypatch.setattr(stripe.Customer, "create", fake_create)

    await session.execute(
        text("UPDATE users SET stripe_customer_id = :cid WHERE id = :uid"),
        {"cid": "cus_existing", "uid": test_user["id"]},
    )
    await session.commit()

    cid = await billing_service.get_or_create_stripe_customer(
        session, user_id=test_user["id"], email=test_user["email"]
    )
    assert cid == "cus_existing"
    assert sdk_calls == []


async def test_missing_customer_creates_via_stripe(session, test_user, monkeypatch) -> None:
    sdk_calls: list[dict] = []

    def fake_create(**kwargs):
        sdk_calls.append(kwargs)
        return type("Customer", (), {"id": "cus_new_id"})()

    import stripe
    monkeypatch.setattr(stripe.Customer, "create", fake_create)

    cid = await billing_service.get_or_create_stripe_customer(
        session, user_id=test_user["id"], email=test_user["email"]
    )
    assert cid == "cus_new_id"
    assert len(sdk_calls) == 1
    assert sdk_calls[0]["email"] == test_user["email"]
    assert sdk_calls[0]["metadata"] == {"user_id": str(test_user["id"])}

    # Persisted.
    row = (
        await session.execute(
            text("SELECT stripe_customer_id FROM users WHERE id = :u"),
            {"u": test_user["id"]},
        )
    ).first()
    assert row.stripe_customer_id == "cus_new_id"
