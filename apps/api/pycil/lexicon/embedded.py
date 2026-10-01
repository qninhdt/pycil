"""Single API-side adapter over Lexi's public capability surface."""

from typing import Any

from lexi_ai import Lexicon

from pycil.lexicon.contracts import LexiReader


def create_lexicon_reader(lexicon: Lexicon) -> LexiReader:
    """Return reads plus the provider-backed synchronous grading seam."""
    reader = lexicon.reader()
    if not callable(getattr(lexicon, "engine", None)):
        return reader
    return _ApiLexiReader(lexicon, reader)


def create_embedded_lexicon_reader() -> tuple[Lexicon, LexiReader]:
    """Build one Lexicon and its provider-free reader capability."""
    lexicon = Lexicon.from_settings()
    return lexicon, create_lexicon_reader(lexicon)


class _ApiLexiReader:
    """Keep dictionary reads provider-free while grading rubric answers inline."""

    def __init__(self, lexicon: Lexicon, reader: LexiReader) -> None:
        self._reader = reader
        self._lexicon = lexicon

    def __getattr__(self, name: str) -> Any:
        return getattr(self._reader, name)

    async def evaluate_answer(self, question_id, submission):
        return await self._lexicon.engine().evaluate_answer(question_id, submission)
