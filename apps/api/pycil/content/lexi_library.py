"""Adapters over lexi-ai's optional public capability facades.

Importing ``lexi_ai`` is deferred until this provider-free reader is selected.
"""

from importlib import import_module
from typing import Any, Protocol

from pycil.content.lexi_port import LexiReader
from pycil.content.lexi_types import Entry, Question, Score, SearchResult, SenseView


class LexiconReaderFacade(Protocol):
    async def search(self, query: str) -> list[Any]: ...

    async def get_entry(self, word_id: int) -> Any | None: ...

    async def get_senses(self, sense_ids: list[int]) -> list[Any]: ...

    async def get_question(self, question_id: int) -> Any | None: ...

    async def get_questions_for_sense(self, sense_id: int, fmt: str | None = None) -> list[Any]: ...


class _LexiconReader:
    def __init__(self, reader: LexiconReaderFacade) -> None:
        self._reader = reader

    async def search(self, query: str) -> list[SearchResult]:
        return [_search_result(value) for value in await self._reader.search(query)]

    async def get_entry(self, word_id: int) -> Entry | None:
        value = await self._reader.get_entry(word_id)
        return None if value is None else _entry(value)

    async def get_senses(self, sense_ids: list[int]) -> list[SenseView]:
        return [_sense(value) for value in await self._reader.get_senses(sense_ids)]

    async def get_question(self, question_id: int) -> Question | None:
        value = await self._reader.get_question(question_id)
        return None if value is None else _question(value)

    async def get_question_for_sense(
        self, sense_id: int, question_format: str
    ) -> Question | None:
        values = await self._reader.get_questions_for_sense(sense_id, question_format)
        return _question(values[0]) if values else None


def create_lexicon_reader(lexicon: object) -> LexiReader:
    """Construct and adapt lexi-ai's provider-free public reader facade."""
    return _LexiconReader(_create_lexicon_reader(lexicon))


def create_embedded_lexicon_reader() -> tuple[object, LexiReader]:
    """Build one Lexicon and its API-safe, provider-free read capability."""
    from lexi_ai import Lexicon

    lexicon = Lexicon.from_settings()
    return lexicon, create_lexicon_reader(lexicon)


def _create_lexicon_reader(lexicon: object) -> LexiconReaderFacade:
    try:
        reader_class = import_module("lexi_ai").LexiconReader
    except ImportError as exc:
        raise RuntimeError("lexi_ai must be installed to use the library reader adapter") from exc
    return reader_class(lexicon)


def _search_result(value: Any) -> SearchResult:
    return SearchResult(
        display=str(value.display),
        entry_type=value.entry_type,
        score=float(value.score),
        lexi_word_id=value.lexi_word_id,
        cambridge_id=value.cambridge_id,
        gloss=value.gloss,
    )


def _entry(value: Any) -> Entry:
    return Entry(
        word_id=int(value.word_id),
        display=str(value.display),
        norm=str(value.norm),
        status=str(value.status),
        entry_type=value.entry_type,
        senses=[_sense(sense) for sense in value.senses],
    )


def _sense(value: Any) -> SenseView:
    return SenseView(
        definition=str(value.definition),
        tier=str(value.tier),
        pos=value.pos,
        cefr_level=value.cefr_level,
        sense_id=value.sense_id,
        examples=list(value.examples),
    )


def _question(value: Any) -> Question:
    return Question(
        id=value.id,
        word_id=int(value.word_id),
        sense_id=value.sense_id,
        format=str(value.format),
        answer_kind=str(value.answer_kind),
        payload=dict(value.payload),
    )


def _score(value: Any) -> Score:
    return Score(
        correct=bool(value.correct),
        score=float(value.score),
        kind=str(value.kind),
        feedback=value.feedback,
    )
