"""Single API-side adapter over Lexi's public capability surface."""

from typing import cast

from lexi_ai import Lexicon

from pycil.ports.lexi import LexiReader


def create_lexicon_reader(lexicon: Lexicon) -> LexiReader:
    """Return Lexi's provider-free reader as Pycil's structural capability."""
    return cast(LexiReader, lexicon.reader())


def create_embedded_lexicon_reader() -> tuple[Lexicon, LexiReader]:
    """Build one Lexicon and its provider-free reader capability."""
    lexicon = Lexicon.from_settings()
    return lexicon, create_lexicon_reader(lexicon)
