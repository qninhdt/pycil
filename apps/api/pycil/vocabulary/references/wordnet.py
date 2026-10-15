"""Optional, generation-only corpus evidence; missing local data is acceptable."""

import asyncio
from typing import Any

from pycil.vocabulary.types import WordNetSense


def _lookup(citation: str) -> list[WordNetSense]:
    try:
        import wn  # pyright: ignore[reportMissingImports]
    except ImportError:
        return []

    try:
        formatted = citation.replace(" ", "_")
        synsets: list[Any] = wn.synsets(formatted)[:20]
        if not synsets and " " in citation:
            synsets = wn.synsets(citation)[:20]

        results: list[WordNetSense] = []
        for sense in synsets:
            if sense is not None:
                if callable(getattr(sense, "name", None)):
                    key = str(sense.name())
                else:
                    key = str(getattr(sense, "id", ""))
                pos_attr = getattr(sense, "pos", "")
                pos_val = str(pos_attr() if callable(pos_attr) else pos_attr)
                defn_attr = getattr(sense, "definition", "")
                defn_val = str(defn_attr() if callable(defn_attr) else defn_attr)
                results.append(
                    WordNetSense(
                        key=key,
                        pos=pos_val,
                        definition=defn_val,
                    )
                )
        return results
    except Exception:
        return []


async def lookup(citation: str) -> list[WordNetSense]:
    if not citation or any(char in citation for char in "/{}()"):
        return []
    return await asyncio.to_thread(_lookup, citation)
