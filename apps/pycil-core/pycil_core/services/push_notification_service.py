"""Web push notifications via VAPID (P4 phase 3).

Stores push subscriptions on subscribe, signs WebPush messages on send.
Uses pywebpush so we don't reinvent encryption.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_log = logging.getLogger(__name__)


async def subscribe(
    session: AsyncSession,
    user_id: UUID,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None = None,
) -> int:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO push_subscriptions
                  (user_id, endpoint, p256dh, auth, user_agent)
                VALUES (:u, :ep, :p, :a, :ua)
                ON CONFLICT (user_id, endpoint) DO UPDATE
                  SET p256dh = EXCLUDED.p256dh,
                      auth = EXCLUDED.auth,
                      user_agent = EXCLUDED.user_agent,
                      last_used_at = NOW()
                RETURNING id
                """
            ),
            {"u": user_id, "ep": endpoint, "p": p256dh, "a": auth, "ua": user_agent},
        )
    ).one()
    return int(row.id)


async def unsubscribe(
    session: AsyncSession, user_id: UUID, endpoint: str
) -> bool:
    result = await session.execute(
        text(
            "DELETE FROM push_subscriptions "
            "WHERE user_id = :u AND endpoint = :ep"
        ),
        {"u": user_id, "ep": endpoint},
    )
    return bool(getattr(result, "rowcount", 0))


async def send_to_user(
    session: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    *,
    vapid_private_key: str | None,
    vapid_subject: str | None,
) -> int:
    """Send a push to every active subscription for the user.

    Returns number of successful sends. Subscriptions returning 410 Gone
    are removed automatically.
    """
    if not vapid_private_key or not vapid_subject:
        _log.warning("web_push_skipped_no_vapid")
        return 0
    try:
        from pywebpush import WebPushException, webpush  # type: ignore
    except ImportError:  # pywebpush not installed yet — graceful degrade
        _log.warning("web_push_skipped_pywebpush_missing")
        return 0

    subs = (
        await session.execute(
            text(
                "SELECT id, endpoint, p256dh, auth FROM push_subscriptions "
                "WHERE user_id = :u"
            ),
            {"u": user_id},
        )
    ).all()
    sent = 0
    body = json.dumps(payload)
    for s in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": s.endpoint,
                    "keys": {"p256dh": s.p256dh, "auth": s.auth},
                },
                data=body,
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": vapid_subject},
            )
            sent += 1
        except WebPushException as exc:  # type: ignore[misc]
            status_code = getattr(exc.response, "status_code", None) if exc.response else None
            if status_code == 410:
                await session.execute(
                    text("DELETE FROM push_subscriptions WHERE id = :id"),
                    {"id": s.id},
                )
            else:
                _log.warning(
                    "web_push_send_failed",
                    extra={"err": str(exc)[:200], "endpoint": s.endpoint[:80]},
                )
    return sent
