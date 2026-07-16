"""LexiClient port — the ONLY interface pycil uses to reach lexi-ai.

pycil stores no dictionary content; it references senses/words by opaque id and
reads content through this Protocol. The MVP adapter is in-process
(``lexi_inprocess.py``); the seam allows a later gRPC swap without touching
callers. Types are lexi-ai read models (imported, never redefined).
"""

from typing import Protocol

from lexi_ai import Entry, Score, SearchResult
from lexi_ai.read_models import Question, SenseView


class LexiClient(Protocol):
    async def search(self, query: str) -> list[SearchResult]: ...

    async def generate(self, source: SearchResult | str) -> Entry: ...

    async def get_entry(self, word_id: int) -> Entry | None: ...

    async def word_id_for_sense(self, sense_id: int) -> int | None: ...

    async def get_senses(self, sense_ids: list[int]) -> list[SenseView]: ...

    async def generate_questions(
        self, entry: Entry, formats: list[str], n: int
    ) -> list[Question]: ...

    async def grade(self, question: Question, answer: str) -> Score: ...

    async def get_question(self, question_id: int) -> Question | None: ...

    async def get_question_for_sense(
        self, sense_id: int, question_format: str
    ) -> Question | None: ...
