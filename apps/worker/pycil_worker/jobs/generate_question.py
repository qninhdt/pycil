"""Question supply warm-up: drive lexi's ``prepare_questions`` (not generation).

Supply is warmed per ``(sense_id, difficulty_level, expected_count)`` demand; the
API-side resolver later pulls concrete questions via ``retrieve_question``.  The
warm-up is best-effort — a failure to warm one sense/word never aborts the batch,
and the learner's ``/next`` simply defers until supply lands.
"""

import logging
from collections import defaultdict

from arq import Retry
from lexi_ai.contracts import PrepareDemand

logger = logging.getLogger(__name__)
_MAX_PREPARE_TRIES = 2


async def prepare_questions(ctx: dict, owner_uid: str, demands: list) -> dict:
    """Warm supply with bounded retries for transient reader/provider failures."""
    del owner_uid  # supply is per-word, not per-user
    reader = ctx["lexi_reader"]
    engine = ctx["lexi_engine"]
    failures = 0

    by_word: dict[int, list[PrepareDemand]] = defaultdict(list)
    for entry in demands:
        sense_id, level, count = int(entry[0]), int(entry[1]), int(entry[2])
        try:
            exposure = await reader.retrieve_exposure(sense_id)
        except LookupError:
            continue  # permanently missing/stale sense
        except Exception:
            failures += 1
            continue
        if exposure.word_id is None:
            continue
        by_word[int(exposure.word_id)].append(
            PrepareDemand(
                sense_id=str(sense_id),
                difficulty_level=level,
                expected_count=count,
            )
        )

    prepared = 0
    for word_id, word_demands in by_word.items():
        try:
            report = await engine.prepare_questions(word_id, word_demands)
            prepared += sum(report.produced.values())
        except Exception:
            failures += 1

    if failures:
        job_try = int(ctx.get("job_try", 1))
        if job_try < _MAX_PREPARE_TRIES:
            raise Retry(defer=5)
        logger.error(
            "question supply preparation exhausted",
            extra={"failed_groups": failures, "prepared": prepared},
        )
        return {"status": "failed", "prepared": prepared, "failed": failures}
    return {"status": "done", "prepared": prepared}
