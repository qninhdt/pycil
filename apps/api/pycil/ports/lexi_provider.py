"""Process-local embedded Lexi reader dependency."""

from lexi_ai import Lexicon

from pycil.ports.lexi import LexiReader
from pycil.ports.lexi_embedded import create_embedded_lexicon_reader

_lexicon: Lexicon | None = None
_client: LexiReader | None = None


def create_embedded_lexi_reader() -> tuple[Lexicon, LexiReader]:
    """Build an independent provider-free Lexi reader for this API process."""
    return create_embedded_lexicon_reader()


async def close_embedded_lexicon(lexicon: Lexicon) -> None:
    """Release resources owned by an embedded Lexicon instance."""
    await lexicon.close()


def get_lexi_client() -> LexiReader:
    """Return the API process's embedded reader."""
    global _lexicon, _client
    if _client is None:
        _lexicon, _client = create_embedded_lexi_reader()
    return _client


async def close_lexi_client() -> None:
    global _lexicon, _client
    if _lexicon is not None:
        await close_embedded_lexicon(_lexicon)
    _lexicon = None
    _client = None
