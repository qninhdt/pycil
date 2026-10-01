"""Process-local embedded Lexi reader dependency."""

from lexi_ai import Lexicon

from pycil.lexicon.contracts import LexiReader
from pycil.lexicon.embedded import create_embedded_lexicon_reader

_lexicon: Lexicon | None = None
_client: LexiReader | None = None


def get_lexi_client() -> LexiReader:
    """Return the API process's embedded reader.

    Routes take this through `Depends`, so `dependency_overrides` substitutes it
    for them. Two call sites call it directly instead —
    `assistant/application/tools.py` and `content_facade.py` — and that is not an
    oversight: `@tool` functions are invoked by the LLM runtime inside an
    assistant turn, not by a request, and they open their own session through
    `async_session_factory` for the same reason. There is no request scope for
    FastAPI to resolve a dependency against.

    The consequence to know when writing a test: overriding this on the app does
    not reach the assistant tools. Patch this module's attribute for those (as
    `tests/assistant/` does for `async_session_factory`).
    """
    global _lexicon, _client
    if _client is None:
        _lexicon, _client = create_embedded_lexicon_reader()
    return _client


async def close_lexi_client() -> None:
    global _lexicon, _client
    if _lexicon is not None:
        await _lexicon.close()
    _lexicon = None
    _client = None
