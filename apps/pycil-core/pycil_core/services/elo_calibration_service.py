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

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_log = logging.getLogger(__name__)

MIN_SAMPLE_SIZE = 30
MIN_DELTA_TO_UPDATE = 25
ELO_FLOOR = 200
ELO_CEILING = 2400


async def calibrate_questions(session: AsyncSession) -> int:
    """Run a calibration pass; return number of questions updated."""
    rows = (
        await session.execute(
            text(
                """
                SELECT q.id, q.elo, COUNT(*)::int AS n,
                       AVG(CASE WHEN qa.is_correct THEN 1.0 ELSE 0.0 END) AS p,
                       AVG(uts.elo) AS mean_user_elo
                  FROM questions q
                  JOIN question_answers qa ON qa.question_id = q.id
                  JOIN user_term_stats uts ON uts.user_id = qa.user_id
                                          AND uts.term_id = q.definition_id
                 GROUP BY q.id, q.elo
                HAVING COUNT(*) >= :min_n
                """
            ),
            {"min_n": MIN_SAMPLE_SIZE},
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
        await session.execute(
            text("UPDATE questions SET elo = :e WHERE id = :id"),
            {"e": int(target), "id": r.id},
        )
        updated += 1
    await session.commit()
    _log.info("elo_calibration_done", extra={"updated": updated, "checked": len(rows)})
    return updated
