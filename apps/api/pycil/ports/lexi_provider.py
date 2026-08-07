"""Process-local embedded Lexi reader dependency.

Two functions used to sit between `get_lexi_client` and the adapter it calls:
`create_embedded_lexi_reader`, which forwarded to
`create_embedded_lexicon_reader` verbatim, and `close_embedded_lexicon`, which
awaited `lexicon.close()`. Neither had a production caller — each existed so one
test could monkeypatch this module instead of the adapter next door — so the
construction path was five functions deep to build one reader.

The adapter (`lexi_embedded.create_embedded_lexicon_reader`) is still the seam
worth substituting; it is just patched directly now.
"""

from lexi_ai import Lexicon

from pycil.ports.lexi import LexiReader
from pycil.ports.lexi_embedded import create_embedded_lexicon_reader

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
    `tests/assistant/` does for `async_session_factory` and `get_arq_pool`).
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
