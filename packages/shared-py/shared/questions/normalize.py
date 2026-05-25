"""Unicode-tolerant answer normalization for Write/Fill grading.

Policy (decided in plan phase 10 red-team):
- NFKC normalize: half-width <> full-width, ligatures, etc.
- Whitespace collapse + strip.
- Lowercase.
- DO NOT strip combining marks (accent fold). Diacritic accuracy is part of
  the lesson for ESL learners — `naive` should NOT match `naïve`.
"""
from __future__ import annotations

import unicodedata


def normalize_answer(value: str) -> str:
    if not value:
        return ""
    s = unicodedata.normalize("NFKC", value)
    s = " ".join(s.split())
    return s.lower()
