"""Tiered answer grading for Write + Fill questions.

Tier ladder (cheapest first):
1. exact match against expected/alts → confidence 1.0
2. normalized match (case/punct/whitespace) → 0.95
3. rapidfuzz Levenshtein ≤2 → 0.85
4. LLM-as-judge (gated by LLM_JUDGE_ENABLED) → 0.7 / borderline 0.6

If all tiers fail: returns is_correct=False, confidence=0.9, reason='no_match'.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any


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

    Returns {is_correct, confidence, reason}. Tier 4 (LLM judge) is reported
    via the marker reason ``llm_judge_pending`` so the caller (an async
    request handler) can dispatch to ``llm_judge_service.judge`` and return
    the final verdict.
    """
    candidates = [expected, *(alts or [])]

    if any(user_answer == c for c in candidates):
        return {"is_correct": True, "confidence": 1.0, "reason": "exact"}

    nu = _normalize(user_answer)
    for c in candidates:
        if nu == _normalize(c):
            return {"is_correct": True, "confidence": 0.95, "reason": "normalized"}

    if len(user_answer) <= 64:
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


def merge_judge_verdict(verdict: str, base: dict[str, Any]) -> dict[str, Any]:
    """Combine the tier-1-3 base with an llm_judge_service verdict."""
    if verdict == "correct":
        return {"is_correct": True, "confidence": 0.7, "reason": "llm_judge"}
    if verdict == "borderline":
        return {"is_correct": True, "confidence": 0.6, "reason": "llm_judge_borderline"}
    return {"is_correct": False, "confidence": 0.9, "reason": "llm_judge_no_match"}

