"""Worker-only adapter for Lexi's provider-enabled engine facade."""

from importlib import import_module
from typing import Any, Protocol

from pycil.content.lexi_library import _entry, _question, _score
from pycil.content.lexi_port import LexiWorkerEngine
from pycil.content.lexi_types import Entry, Question, Score, SearchResult


class _EngineFacade(Protocol):
    async def generate_fenced(self, source: Any) -> Any: ...

    async def generate_questions_for_sense(
        self, word_id: int, sense_id: int, formats: list[str], n: int
    ) -> list[Any]: ...

    async def grade_question(self, question_id: int, answer: object) -> Any | None: ...


class _LexiconWorkerEngine:
    def __init__(self, engine: _EngineFacade) -> None:
        self._engine = engine

    async def generate(
        self, source: SearchResult | str, *, idempotency_key: str | None = None
    ) -> Entry:
        del idempotency_key
        return _entry(await self._engine.generate_fenced(source))

    async def generate_questions(
        self, word_id: int, sense_id: int, formats: list[str], n: int
    ) -> list[Question]:
        values = await self._engine.generate_questions_for_sense(word_id, sense_id, formats, n)
        return [_question(value) for value in values]

    async def grade(self, question: Question, answer: str) -> Score:
        if question.id is None:
            raise ValueError("question_requires_persisted_id")
        value = await self._engine.grade_question(question.id, answer)
        if value is None:
            raise ValueError("question_requires_persisted_id")
        return _score(value)


def create_lexicon_worker_engine(lexicon: object) -> LexiWorkerEngine:
    try:
        engine_class = import_module("lexi_ai").LexiconEngine
    except ImportError as exc:
        raise RuntimeError("lexi_ai must be installed to use the library worker adapter") from exc
    return _LexiconWorkerEngine(engine_class(lexicon))
