"""Worker adapter over Lexi's public provider-enabled capability."""

from typing import cast

from lexi_ai import Lexicon
from pycil.content.lexi_port import LexiWorkerEngine


def create_lexicon_worker_engine(lexicon: Lexicon) -> LexiWorkerEngine:
    """Return the public engine facade without importing Lexi internals."""
    return cast(LexiWorkerEngine, lexicon.engine())
