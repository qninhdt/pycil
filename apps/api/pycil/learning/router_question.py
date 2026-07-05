"""Asymmetric question-format router (docs/designs/fsrs-learning-engine.md §6).

Mastery sets a difficulty CAP: the learner may get an EASIER format but never a
harder one than their mastery warrants. A binary engine can't tell "forgot the
word" from "format too hard", so failing an over-hard question would wrongly
penalize stability; offering an easier one only adds mild safe-direction noise.

pycil's three conceptual types map to lexi-ai's four real format ids:
  mcq  → definition_mcq | contextual_mcq
  fill → cloze
  write→ use_in_sentence
"""

import hashlib

# lexi-ai real format ids (lexi_ai/constants.py QUESTION_FORMATS).
DEFINITION_MCQ = "definition_mcq"
CONTEXTUAL_MCQ = "contextual_mcq"
CLOZE = "cloze"
USE_IN_SENTENCE = "use_in_sentence"

# Conceptual type → weighted lexi format ids per mastery band.
# Rows never exceed the band's cap, so no separate cap check is needed.
_MCQ = "mcq"
_FILL = "fill"
_WRITE = "write"

# (conceptual_type, weight) rows by band; weights sum to 100.
_BAND_LOW = [(_MCQ, 100)]  # mastery < 30
_BAND_MID = [(_FILL, 80), (_MCQ, 20)]  # 30-65
_BAND_HIGH = [(_WRITE, 70), (_FILL, 20), (_MCQ, 10)]  # > 65

# Conceptual type → lexi format id (mcq resolves to definition vs contextual by band).
_TYPE_TO_FORMAT = {
    _FILL: CLOZE,
    _WRITE: USE_IN_SENTENCE,
}


def _band(mastery: int) -> list[tuple[str, int]]:
    if mastery < 30:
        return _BAND_LOW
    if mastery <= 65:
        return _BAND_MID
    return _BAND_HIGH


def _weighted_pick(rows: list[tuple[str, int]], seed: str) -> str:
    """Deterministic weighted pick (seeded by sense+session so it's reproducible)."""
    total = sum(w for _, w in rows)
    # Stable hash → [0, total). hashlib (not hash()) so it's process-independent.
    digest = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    point = digest % total
    acc = 0
    for kind, weight in rows:
        acc += weight
        if point < acc:
            return kind
    return rows[-1][0]


def choose_format(mastery: int, seed: str) -> str:
    """Return a lexi format id at or below the mastery cap.

    ``seed`` (e.g. f"{sense_id}:{session_id}") makes the pick deterministic for a
    given sense within a session, so a re-fetch of "next" is stable.
    """
    band = _band(mastery)
    kind = _weighted_pick(band, seed)
    if kind == _MCQ:
        # Low band uses definition MCQ (recognition); higher bands that still roll
        # mcq get the harder contextual MCQ.
        return DEFINITION_MCQ if mastery < 30 else CONTEXTUAL_MCQ
    return _TYPE_TO_FORMAT[kind]
