"""LexiClient port — the ONLY interface pycil uses to reach lexi-ai.

pycil stores no dictionary content; it references senses/words by opaque id and
reads content through this Protocol. DTOs are Pycil-owned projections of the
versioned Lexi HTTP contract, never Lexi's local ORM/read models.
"""

from typing import Protocol

from pycil.content.lexi_types import Entry, Question, Score, SearchResult, SenseView


class LexiClient(Protocol):
    async def readiness(self) -> bool: ...

    async def search(self, query: str) -> list[SearchResult]: ...

    async def generate(self, source: SearchResult | str) -> Entry: ...

    async def get_entry(self, word_id: int) -> Entry | None: ...

    async def get_senses(self, sense_ids: list[int]) -> list[SenseView]: ...

    async def generate_questions(
        self, word_id: int, sense_id: int, formats: list[str], n: int
    ) -> list[Question]: ...

    async def grade(self, question: Question, answer: str) -> Score: ...

    async def get_question(self, question_id: int) -> Question | None: ...

    async def get_question_for_sense(
        self, sense_id: int, question_format: str
    ) -> Question | None: ...
