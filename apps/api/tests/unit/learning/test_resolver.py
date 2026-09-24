"""Resolver: level-fallback order, is_fallback, exposure path (acceptance #8)."""

import random

import pytest
from lexi_ai.contracts import Flashcard

from pycil.learning import resolver
from tests.support.lexi_fakes import FakeLexiReader

pytestmark = pytest.mark.asyncio


async def test_resolve_returns_requested_level_when_available():
    reader = FakeLexiReader()
    reader.add_supply(1, 2, "cloze")
    resolved = await resolver.resolve(reader, 1, 2, frozenset(), random.Random(0))
    assert resolved is not None
    assert resolved.served_level == 2
    assert resolved.requested_level == 2
    assert resolved.is_fallback is False


async def test_resolve_falls_back_to_lower_level():
    reader = FakeLexiReader()
    # Only level-1 supply exists; request level 3 -> falls back to 1.
    reader.add_supply(1, 1, "definition_mcq")
    resolved = await resolver.resolve(reader, 1, 3, frozenset(), random.Random(0))
    assert resolved is not None
    assert resolved.served_level == 1
    assert resolved.requested_level == 3
    assert resolved.is_fallback is True


async def test_resolve_never_exceeds_requested_level():
    reader = FakeLexiReader()
    reader.add_supply(1, 4, "use_in_sentence")  # higher-level supply exists
    reader.add_supply(1, 1, "definition_mcq")
    resolved = await resolver.resolve(reader, 1, 1, frozenset(), random.Random(0))
    assert resolved is not None
    assert resolved.served_level == 1  # never jumps up to level 4


async def test_resolve_none_when_no_eligible_supply():
    reader = FakeLexiReader()
    resolved = await resolver.resolve(reader, 1, 3, frozenset(), random.Random(0))
    assert resolved is None


async def test_resolve_respects_excluded_ids():
    reader = FakeLexiReader()
    (qid,) = reader.add_supply(1, 1, "definition_mcq")
    resolved = await resolver.resolve(reader, 1, 1, frozenset({qid}), random.Random(0))
    assert resolved is None


async def test_resolve_exposure_never_fallback():
    reader = FakeLexiReader()
    resolved = await resolver.resolve_exposure(reader, 5)
    assert resolved.served_level == 0
    assert resolved.is_fallback is False
    assert isinstance(resolved.question.render, Flashcard)
