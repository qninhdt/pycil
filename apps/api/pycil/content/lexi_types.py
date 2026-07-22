"""Pycil-owned DTOs for the embedded Lexi library boundary.

These are deliberately small projections.  Pycil neither imports Lexi ORM/read
models nor relies on Lexi's local database implementation.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SearchResult:
    display: str
    entry_type: str | None
    score: float = 0.0
    lexi_word_id: int | None = None
    cambridge_id: int | None = None
    gloss: str | None = None


@dataclass(frozen=True)
class SenseView:
    definition: str
    tier: str
    pos: str | None
    cefr_level: str | None
    sense_id: int | None = None
    examples: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Entry:
    word_id: int
    display: str
    norm: str
    status: str
    entry_type: str | None
    senses: list[SenseView] = field(default_factory=list)


@dataclass(frozen=True)
class Question:
    id: int | None
    word_id: int
    sense_id: int | None
    format: str
    answer_kind: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class Score:
    correct: bool
    score: float
    kind: str
    feedback: str | None = None
