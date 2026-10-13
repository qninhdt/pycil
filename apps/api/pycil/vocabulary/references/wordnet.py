"""Optional, generation-only corpus evidence; missing local data is acceptable."""

import asyncio
from threading import Lock
from typing import Any, cast

from pycil.vocabulary.types import WordNetSense

lock = Lock()


def _lookup(citation: str) -> list[WordNetSense]:
    from nltk.corpus import wordnet  # pyright: ignore[reportMissingTypeStubs]

    # The lazy corpus reader shares seekable files between lookup threads.
    with lock:
        try:
            synsets = cast(list[Any], wordnet.synsets(citation.replace(" ", "_"))[:20])  # pyright: ignore[reportUnknownMemberType]
            results: list[WordNetSense] = []
            for sense in synsets:
                if sense is not None:
                    results.append(
                        WordNetSense(
                            key=str(sense.name()),
                            pos=str(sense.pos()),
                            definition=str(sense.definition()),
                        )
                    )
            return results
        except LookupError:
            return []


async def lookup(citation: str) -> list[WordNetSense]:
    if not citation or any(char in citation for char in "/{}()"):
        return []
    return await asyncio.to_thread(_lookup, citation)
