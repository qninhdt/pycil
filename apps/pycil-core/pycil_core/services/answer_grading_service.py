"""Tiered answer grading for Write + Fill questions.

Tier ladder (cheapest first):
1. exact match against expected/alts → confidence 1.0
2. normalized match (case/punct/whitespace) → 0.95
3. rapidfuzz Levenshtein ≤2 → 0.85
4. LLM-as-judge (deferred to v0.3) → 0.7

If all tiers fail: returns is_correct=False, confidence=0.9, reason='no_match'.
"""
from __future__ import annotations

import re
import unicodedata


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFC", s).strip().lower()
    s = re.sub(r"[^\w\s]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s)
    return s


def grade(
    *,
    expected: str,
    alts: list[str] | None,
    user_answer: str,
    use_llm_fallback: bool = False,
) -> dict:
    """Grade a free-text answer against expected + alternates.

    Returns {is_correct, confidence, reason}.
    """
    candidates = [expected, *(alts or [])]

    if any(user_answer == c for c in candidates):
        return {"is_correct": True, "confidence": 1.0, "reason": "exact"}

    nu = _normalize(user_answer)
    for c in candidates:
        if nu == _normalize(c):
            return {"is_correct": True, "confidence": 0.95, "reason": "normalized"}

    if len(user_answer) <= 32:
        try:
            from rapidfuzz.distance import Levenshtein

            for c in candidates:
                if Levenshtein.distance(nu, _normalize(c)) <= 2:
                    return {
                        "is_correct": True,
                        "confidence": 0.85,
                        "reason": "fuzzy",
                    }
        except ImportError:
            pass

    if use_llm_fallback:
        return {
            "is_correct": False,
            "confidence": 0.7,
            "reason": "llm_judge_pending",
        }

    return {"is_correct": False, "confidence": 0.9, "reason": "no_match"}
