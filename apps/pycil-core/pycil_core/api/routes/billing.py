"""Stripe billing endpoints: checkout, portal, webhook.

Webhook handler reads raw bytes via `await request.body()` — Stripe signs
the literal body, any Pydantic round-trip invalidates the signature.
Webhook idempotency: insert event_id BEFORE dispatch.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import text

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.config import get_settings
from pycil_core.services import billing_service


router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/checkout")
async def create_checkout(
    user: UserDep, session: SessionDep
) -> dict:
    s = get_settings()
    secret = getattr(s, "stripe_secret_key", None)
    price_id = getattr(s, "stripe_price_id_pro", None)
    if not secret or not price_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "billing_not_configured")

    import stripe

    stripe.api_key = secret
    customer_id = await billing_service.get_or_create_stripe_customer(
        session, user_id=user.id, email=user.email
    )
    sess = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=getattr(s, "stripe_success_url", "/profile?billing=success"),
        cancel_url=getattr(s, "stripe_cancel_url", "/profile?billing=cancelled"),
        metadata={"user_id": str(user.id)},
        subscription_data={"metadata": {"user_id": str(user.id)}},
    )
    return {"url": sess.url}


@router.post("/webhook")
async def webhook(request: Request, session: SessionDep) -> dict:
    """Stripe webhook receiver. RAW BODY required for signature verification."""
    s = get_settings()
    webhook_secret = getattr(s, "stripe_webhook_secret", None)
    if not webhook_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "webhook_not_configured")

    payload_bytes = await request.body()
    sig = request.headers.get("stripe-signature", "")

    import stripe

    try:
        event = stripe.Webhook.construct_event(payload_bytes, sig, webhook_secret)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_signature")

    # Insert event_id BEFORE dispatch within ONE transaction. If dispatch
    # raises, the txn rolls back and Stripe retries; on retry the PK
    # conflict short-circuits to 200. Idempotent + lossless.
    from sqlalchemy.exc import IntegrityError

    try:
        await session.execute(
            text(
                "INSERT INTO stripe_webhook_events (event_id) VALUES (:eid)"
            ),
            {"eid": event["id"]},
        )
    except IntegrityError:
        await session.rollback()
        return {"ok": True, "duplicate": True}

    etype = event.get("type", "")
    obj = event.get("data", {}).get("object", {})
    metadata = obj.get("metadata") or {}
    user_id = metadata.get("user_id")
    pe_epoch = obj.get("current_period_end")
    pe_int = int(pe_epoch) if isinstance(pe_epoch, (int, float, str)) and pe_epoch else None
    event_created = int(event.get("created") or 0)
    event_id_str = str(event.get("id") or "")

    if etype == "customer.subscription.created" and user_id:
        await billing_service.upsert_subscription(
            session,
            user_id=user_id,
            tier="pro",
            stripe_subscription_id=obj.get("id"),
            current_period_end_epoch=pe_int,
            status_str="active",
            event_created_epoch=event_created,
            event_id=event_id_str,
        )
    elif etype == "customer.subscription.updated" and user_id:
        await billing_service.upsert_subscription(
            session,
            user_id=user_id,
            tier="pro",
            stripe_subscription_id=obj.get("id"),
            current_period_end_epoch=pe_int,
            status_str=str(obj.get("status") or "active"),
            event_created_epoch=event_created,
            event_id=event_id_str,
        )
    elif etype == "customer.subscription.deleted" and user_id:
        await billing_service.upsert_subscription(
            session,
            user_id=user_id,
            tier="free",
            stripe_subscription_id=obj.get("id"),
            current_period_end_epoch=None,
            status_str="cancelled",
            event_created_epoch=event_created,
            event_id=event_id_str,
        )

    await session.commit()
    return {"ok": True}
