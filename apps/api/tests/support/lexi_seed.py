"""A small real Lexi corpus for the system level.

Question supply draws multiple-choice distractors from **other words** — siblings
sharing a topic, or semantic neighbours. A dictionary holding one word therefore
cannot produce a choice item at all, and the supply job correctly reports that as
``question_supply_unavailable`` rather than inventing a question. That is the
product behaving properly; what it means for a test is that a study journey needs a
population, not a single word.

The corpus is built through the product's own path — ``POST /v1/word-generations``,
performed by the real worker against the real provider fixture — rather than by
writing dictionary rows directly. Seeding rows would bypass the generation and
persistence code the study journeys depend on, and a corpus that arrived by a
different route can be well-formed in ways the real one is not.

Word choice is deliberate rather than arbitrary: the words are ordinary, distinct
English headwords, so the fixture's provider answers each one and the entries do not
collide on ``match_key``.
"""

from __future__ import annotations

import asyncio
from typing import Any

#: Enough words that every assessment type has siblings to draw on, and few enough
#: that seeding stays a fraction of the suite's runtime. One would be too few — that
#: is the whole reason this module exists.
CORPUS_WORDS: tuple[str, ...] = (
    "resilient",
    "tenacious",
    "meticulous",
    "pragmatic",
    "elusive",
    "vivid",
)

_TERMINAL = {"done", "failed", "expired"}


async def generate_word(caller: Any, word: str, *, timeout: float = 120.0) -> int:
    """Generate one word through the API and return its first sense id.

    The caller is an ``Api``; the work is the product's, so a journey that needs a
    sense never constructs one.
    """
    created = await caller.ok("POST", "/v1/word-generations", json={"query": word})
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        receipt = await caller.ok("GET", f"/v1/jobs/{created['taskId']}")
        if receipt["status"] in _TERMINAL:
            assert receipt["status"] == "done", receipt
            return receipt["result"]["senseIds"][0]
        await asyncio.sleep(0.25)
    raise AssertionError(f"generation of {word!r} never finished")


async def seed(caller: Any, words: tuple[str, ...] = CORPUS_WORDS) -> dict[str, int]:
    """Generate every corpus word and return ``word -> sense_id``.

    Sequential rather than concurrent: the point is a populated dictionary, and
    racing the generator would test single-flight instead of building a corpus.
    """
    return {word: await generate_word(caller, word) for word in words}
