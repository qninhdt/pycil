"""Variant-seed consumer (P3 phase 1).

`questions.variant_seed` was added in v0.2 but the worker doesn't use it
to diversify wrong-answer distractors. This service computes the seed
from `(question_id, user_id, hour_bucket)` so the same user gets a
different distractor set on subsequent reviews of the same MCQ — without
re-querying the LLM.
"""
from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from uuid import UUID


def compute_variant_seed(question_id: int, user_id: UUID, hour_bucket: int) -> int:
    raw = f"{question_id}:{user_id}:{hour_bucket}".encode()
    digest = hashlib.sha256(raw).digest()[:4]
    return int.from_bytes(digest, "big")


def shuffle_options(
    options: Sequence[str], correct_index: int, seed: int
) -> tuple[list[str], int]:
    """Return (shuffled options, new index of correct).

    Deterministic for a given seed so re-display of the same question on
    the same hour bucket renders identically (no flicker).
    """
    rng = random.Random(seed)
    indexed = list(enumerate(options))
    rng.shuffle(indexed)
    new_index = next(i for i, (orig, _) in enumerate(indexed) if orig == correct_index)
    return [v for _, v in indexed], new_index
