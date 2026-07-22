"""Pycil-owned capabilities for reading and operating Lexi content.

Pycil stores no dictionary content; it references senses/words by opaque id and
uses these Pycil-owned DTO projections. API readers and worker engines stay
separate so no process accidentally gains provider-write capability.
"""

from typing import Protocol

from pycil.content.lexi_types import Entry, Question, Score, SearchResult, SenseView


class LexiReader(Protocol):
    async def search(self, query: str) -> list[SearchResult]: ...

    async def get_entry(self, word_id: int) -> Entry | None: ...

    async def get_senses(self, sense_ids: list[int]) -> list[SenseView]: ...

    async def get_question(self, question_id: int) -> Question | None: ...

    async def get_question_for_sense(
        self, sense_id: int, question_format: str
    ) -> Question | None: ...


class LexiWorkerEngine(Protocol):
    async def generate(
        self, source: SearchResult | str, *, idempotency_key: str | None = None
    ) -> Entry: ...

    async def generate_questions(
        self, word_id: int, sense_id: int, formats: list[str], n: int
    ) -> list[Question]: ...

    async def grade(self, question: Question, answer: str) -> Score: ...


class LexiClient(LexiReader, LexiWorkerEngine, Protocol):
    """Combined capability required only by legacy synchronous grading paths."""
