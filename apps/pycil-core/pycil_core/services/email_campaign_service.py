"""Reactivation + digest email orchestration (P4 phases 4-6).

Picks users who:
- streak_break:        had >=3 streak days then missed yesterday;
- weekly_digest:       active in last 7d (gentle "this week you learned");
- reactivation:        no question_answers in 14d, joined >14d ago.

Templates live alongside this module; all sends route through email_service.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil_core.services.email_service import get_transport, record_event

_log = logging.getLogger(__name__)


async def streak_break_targets(
    session: AsyncSession,
) -> Sequence[tuple[UUID, str, int]]:
    """Users who broke a streak >=3 days yesterday. Returns (id, email, streak)."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    rows = (
        await session.execute(
            text(
                """
                SELECT u.id, u.email, u.current_streak
                  FROM users u
                 WHERE u.current_streak >= 3
                   AND u.last_active_at >= :y_start
                   AND u.last_active_at <  :today_start
                   AND u.email IS NOT NULL
                """
            ),
            {"y_start": yesterday_start, "today_start": today_start},
        )
    ).all()
    return [(r.id, r.email, int(r.current_streak)) for r in rows]


async def weekly_digest_targets(
    session: AsyncSession,
) -> Sequence[tuple[UUID, str, int]]:
    """Active in the last 7 days. (id, email, answers_count)."""
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    rows = (
        await session.execute(
            text(
                """
                SELECT u.id, u.email,
                       (SELECT COUNT(*) FROM question_answers qa
                         WHERE qa.user_id = u.id
                           AND qa.answered_at >= :w_ago)::int AS answers
                  FROM users u
                 WHERE u.email IS NOT NULL
                   AND u.last_active_at >= :w_ago
                """
            ),
            {"w_ago": week_ago},
        )
    ).all()
    return [(r.id, r.email, int(r.answers)) for r in rows if int(r.answers) > 0]


async def reactivation_targets(
    session: AsyncSession,
) -> Sequence[tuple[UUID, str]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    rows = (
        await session.execute(
            text(
                """
                SELECT u.id, u.email
                  FROM users u
                 WHERE u.email IS NOT NULL
                   AND u.created_at < :cutoff
                   AND COALESCE(u.last_active_at, u.created_at) < :cutoff
                """
            ),
            {"cutoff": cutoff},
        )
    ).all()
    return [(r.id, r.email) for r in rows]


async def send_streak_break(session: AsyncSession) -> int:
    transport = get_transport()
    sent = 0
    for user_id, email, streak in await streak_break_targets(session):
        message_id = await transport.send(
            to=email,
            subject=f"Don't lose your {streak}-day Pycil streak!",
            text_body=(
                f"Hey,\n\nYou had a {streak}-day learning streak going. "
                "Five minutes today brings it back.\n\n— Pycil"
            ),
        )
        await record_event(
            session,
            provider="stub",
            message_id=message_id,
            event="streak_break_sent",
            user_id=user_id,
            payload={"streak": streak},
        )
        sent += 1
    await session.commit()
    _log.info("streak_break_emails_sent", extra={"count": sent})
    return sent
