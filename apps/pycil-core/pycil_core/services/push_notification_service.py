"""Web push notifications via VAPID (P4 phase 3).

Stores push subscriptions on subscribe, signs WebPush messages on send.
Uses pywebpush so we don't reinvent encryption.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.db import PushSubscription

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
    stmt = insert(PushSubscription).values(
        user_id=user_id,
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth,
        user_agent=user_agent,
    )
    row = (
        await session.exec(
            stmt.on_conflict_do_update(
                index_elements=[PushSubscription.user_id, PushSubscription.endpoint],
                set_={
                    "p256dh": stmt.excluded.p256dh,
                    "auth": stmt.excluded.auth,
                    "user_agent": stmt.excluded.user_agent,
                    "last_used_at": func.now(),
                },
            ).returning(PushSubscription.id)
        )
    ).one()
    return int(row[0] if isinstance(row, tuple) else row.id)


async def unsubscribe(
    session: AsyncSession, user_id: UUID, endpoint: str
) -> bool:
    result = await session.exec(
        delete(PushSubscription).where(
            PushSubscription.user_id == user_id,
            PushSubscription.endpoint == endpoint,
        )
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
        await session.exec(
            select(
                PushSubscription.id,
                PushSubscription.endpoint,
                PushSubscription.p256dh,
                PushSubscription.auth,
            ).where(PushSubscription.user_id == user_id)
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
                await session.exec(
                    delete(PushSubscription).where(PushSubscription.id == s.id)
                )
            else:
                _log.warning(
                    "web_push_send_failed",
                    extra={"err": str(exc)[:200], "endpoint": s.endpoint[:80]},
                )
    return sent
