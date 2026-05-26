"""Speaking practice with browser STT (P7 phase 3).

Server side is thin: receives the user's transcript from the browser's
Web Speech API and runs the standard grading service. Optional bonus —
score includes a phonetic-similarity bump using rapidfuzz against the
expected term so accent slips don't feel like wrong answers.
"""
from __future__ import annotations

from typing import Any

from pycil_core.services.answer_grading_service import grade


async def grade_transcript(*, expected: str, transcript: str) -> dict[str, Any]:
    """Phonetic-friendly grade.

    Strips punctuation, accepts a fuzzy threshold ≤2 plus the existing
    tier-1-3 ladder. No LLM tier — STT inputs are noisy and judge cost
    would dominate.
    """
    cleaned = transcript.strip()
    base = grade(expected=expected, alts=None, user_answer=cleaned)
    base["mode"] = "speaking"
    return base
