"""XP, streak, badge, and level math.

Hooks into `learning_service.submit_answer` to award XP per response,
tick the daily streak, and check unlock predicates against the locked
badge list. Notifications fire via `notification_service` on unlock.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil_core.services import notification_service


XP_DELTA = {"correct_new": 10, "correct_review": 5, "wrong": 2}

LEVEL_TABLE = [
    (1, 0), (2, 100), (3, 250), (4, 500), (5, 1000),
    (6, 2000), (7, 4000), (8, 7000), (9, 11000), (10, 16000),
    (11, 22000),
]

BADGES = ["first_term", "first_session", "7_day_streak", "30_day_streak",
          "polyglot", "mastery_10"]


def compute_level(xp: int) -> int:
    level = 1
    for lvl, threshold in LEVEL_TABLE:
        if xp >= threshold:
            level = lvl
    return level


async def award_xp(session: AsyncSession, *, user_id: UUID, delta: int) -> None:
    """Add `delta` XP to user; recompute level atomically.

    Single UPDATE: xp increment + level derivation share the same row-lock,
    so concurrent awards cannot publish a stale `level` based on pre-increment xp.
    """
    await session.execute(
        text(
            """
            UPDATE users
               SET xp_total = xp_total + :delta,
                   level = CASE
                       WHEN xp_total + :delta >= 22000 THEN 11
                       WHEN xp_total + :delta >= 16000 THEN 10
                       WHEN xp_total + :delta >= 11000 THEN 9
                       WHEN xp_total + :delta >=  7000 THEN 8
                       WHEN xp_total + :delta >=  4000 THEN 7
                       WHEN xp_total + :delta >=  2000 THEN 6
                       WHEN xp_total + :delta >=  1000 THEN 5
                       WHEN xp_total + :delta >=   500 THEN 4
                       WHEN xp_total + :delta >=   250 THEN 3
                       WHEN xp_total + :delta >=   100 THEN 2
                       ELSE 1
                   END,
                   updated_at = NOW()
             WHERE id = :uid
            """
        ),
        {"uid": user_id, "delta": delta},
    )
    await session.commit()


async def tick_streak(session: AsyncSession, *, user_id: UUID) -> int:
    """Increment streak if last_session_date == today-1; reset if older.

    Returns the new streak_days value.
    """
    row = (
        await session.execute(
            text(
                """
                UPDATE users
                   SET streak_days = CASE
                            WHEN last_session_date IS NULL THEN 1
                            WHEN last_session_date = CURRENT_DATE THEN streak_days
                            WHEN last_session_date = CURRENT_DATE - INTERVAL '1 day'
                                THEN streak_days + 1
                            ELSE 1
                       END,
                       last_session_date = CURRENT_DATE,
                       updated_at = NOW()
                 WHERE id = :uid
                RETURNING streak_days
                """
            ),
            {"uid": user_id},
        )
    ).first()
    await session.commit()
    return int(row.streak_days) if row else 0


async def check_badges(session: AsyncSession, *, user_id: UUID) -> list[str]:
    """Evaluate badge predicates; persist newly-unlocked + emit notifications.

    Returns list of newly-unlocked badge ids.
    """
    user_row = (
        await session.execute(
            text(
                "SELECT badges, streak_days FROM users WHERE id = :uid"
            ),
            {"uid": user_id},
        )
    ).first()
    if user_row is None:
        return []
    owned = set(user_row.badges or [])

    unlocked: list[str] = []

    if "first_term" not in owned:
        n = (await session.execute(
            text(
                "SELECT COUNT(*) AS c FROM deck_definitions dd "
                "JOIN nodes n ON n.id = dd.deck_id "
                "WHERE n.author_id = :uid"
            ),
            {"uid": user_id},
        )).one().c
        if n >= 1:
            unlocked.append("first_term")

    if "7_day_streak" not in owned and (user_row.streak_days or 0) >= 7:
        unlocked.append("7_day_streak")
    if "30_day_streak" not in owned and (user_row.streak_days or 0) >= 30:
        unlocked.append("30_day_streak")

    if not unlocked:
        return []

    new_badges = list(owned | set(unlocked))
    import json as _json
    await session.execute(
        text(
            "UPDATE users SET badges = CAST(:b AS jsonb) WHERE id = :uid"
        ),
        {"uid": user_id, "b": _json.dumps(new_badges)},
    )
    await session.commit()

    for badge in unlocked:
        await notification_service.create(
            session, user_id=user_id, kind="badge_unlocked", payload={"badge": badge}
        )
    return unlocked
