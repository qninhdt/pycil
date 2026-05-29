"""Per-question ELO calibration cron (P3 phase 2).

Daily/weekly job: for each question with sufficient sample size,
recompute its ELO rating using the global pool of (user_elo, correct/wrong)
observations. Increases scheduling fairness — questions with high-difficulty
ratings get scheduled to high-ELO users.

Algorithm: simplified Bradley-Terry — for each question with N answers and
P% correct rate, target ELO = mean_user_elo - 400 * log10((1 - P) / P).
Clamped to [200, 2400] and only updated when |delta| > 25.
"""
from __future__ import annotations

import logging
import math

from sqlalchemy import case, func, update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.db import Question, Response, UserTermStat

_log = logging.getLogger(__name__)

MIN_SAMPLE_SIZE = 30
MIN_DELTA_TO_UPDATE = 25
ELO_FLOOR = 200
ELO_CEILING = 2400


async def calibrate_questions(session: AsyncSession) -> int:
    """Run a calibration pass; return number of questions updated."""
    rows = (
        await session.exec(
            select(
                Question.id,
                Question.elo,
                func.count(Response.id).label("n"),
                func.avg(case((Response.is_correct.is_(True), 1.0), else_=0.0)).label("p"),
                func.avg(UserTermStat.mastery_score).label("mean_user_elo"),
            )
            .join(Response, Response.question_id == Question.id)
            .join(
                UserTermStat,
                (UserTermStat.user_id == Response.user_id)
                & (UserTermStat.definition_id == Question.definition_id),
            )
            .group_by(Question.id, Question.elo)
            .having(func.count(Response.id) >= MIN_SAMPLE_SIZE)
        )
    ).all()
    updated = 0
    for r in rows:
        p = max(0.01, min(0.99, float(r.p)))
        mean_elo = float(r.mean_user_elo or 800)
        target = mean_elo - 400 * math.log10((1 - p) / p)
        target = max(ELO_FLOOR, min(ELO_CEILING, target))
        delta = abs(target - float(r.elo))
        if delta < MIN_DELTA_TO_UPDATE:
            continue
        await session.exec(
            update(Question).where(Question.id == r.id).values(elo=int(target))
        )
        updated += 1
    await session.commit()
    _log.info("elo_calibration_done", extra={"updated": updated, "checked": len(rows)})
    return updated
