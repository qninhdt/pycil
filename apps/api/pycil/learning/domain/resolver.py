"""Difficulty fallback over Lexi's public, answer-safe question contracts."""

from __future__ import annotations

import random
from dataclasses import dataclass

from pycil.ports.lexi import LexiReader, PresentedQuestion


@dataclass(frozen=True)
class ResolvedQuestion:
    question: PresentedQuestion
    requested_level: int
    served_level: int
    is_fallback: bool


def _assessment_type_ids(reader: LexiReader, level: int) -> list[str]:
    return [
        info.type_id
        for info in reader.question_types()
        if level in info.difficulty_levels and info.interaction == "assessment"
    ]


async def resolve(
    reader: LexiReader,
    sense_id: int,
    requested_level: int,
    excluded_ids: frozenset[int],
    rng: random.Random | None = None,
) -> ResolvedQuestion | None:
    picker = rng if rng is not None else random.Random()
    for level in range(requested_level, 0, -1):
        type_ids = _assessment_type_ids(reader, level)
        picker.shuffle(type_ids)
        for type_id in type_ids:
            question = await reader.retrieve_question(
                sense_id, level, excluded_ids, type_id
            )
            if question is not None:
                return ResolvedQuestion(
                    question=question,
                    requested_level=requested_level,
                    served_level=level,
                    is_fallback=level < requested_level,
                )
    return None


async def resolve_exposure(reader: LexiReader, sense_id: int) -> ResolvedQuestion:
    question = await reader.retrieve_exposure(sense_id)
    return ResolvedQuestion(
        question=question,
        requested_level=0,
        served_level=0,
        is_fallback=False,
    )
