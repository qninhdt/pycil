"""Content dependencies: the shared LexiClient instance.

A single Lexicon (bound to lexi-ai's DB) is built once per process and reused.
``lexicon.init()`` is run at startup (Phase 11); tests override this dependency
with a fake LexiClient.
"""

from pycil.content.lexi_inprocess import InProcessLexiClient, build_lexicon
from pycil.content.lexi_port import LexiClient

_client: InProcessLexiClient | None = None


def get_lexi_client() -> LexiClient:
    global _client
    if _client is None:
        _client = InProcessLexiClient(build_lexicon())
    return _client
