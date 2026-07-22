"""Process-local embedded Lexi reader dependency."""

from pycil.content.lexi_library import create_embedded_lexicon_reader
from pycil.content.lexi_port import LexiReader

_lexicon: object | None = None
_client: LexiReader | None = None


def create_embedded_lexi_reader() -> tuple[object, LexiReader]:
    """Build an independent provider-free Lexi reader for this API process."""
    return create_embedded_lexicon_reader()


async def close_embedded_lexicon(lexicon: object) -> None:
    """Release the pool owned by an embedded Lexicon instance."""
    engine = getattr(lexicon, "_engine", None)
    if engine is not None:
        await engine.dispose()


def get_lexi_client() -> LexiReader:
    """Return the API process's embedded reader.

    The historical name is retained only because it is the current FastAPI
    dependency callable; it no longer creates or calls an HTTP client.
    """
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
