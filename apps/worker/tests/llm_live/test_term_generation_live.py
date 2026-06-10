"""Live contract: term generation against a real model.

Proves the generate_term.md prompt + TermGenerationOutput schema + json_mode
parse path round-trips through a live model and yields a structurally valid,
on-topic enrichment. Skipped unless RUN_LLM_LIVE=1 (see conftest).
"""
from __future__ import annotations

import pytest

from worker.llm.openrouter import invoke_with_fallback
from worker.prompts import render
from worker.schemas.term_generation import TermGenerationOutput

pytestmark = pytest.mark.llm_live


def _is_cefr(value: str) -> bool:
    return value in {"A1", "A2", "B1", "B2", "C1", "C2"}


async def test_generate_term_live_structure_and_topicality() -> None:
    prompt = render("generate_term.md", term_value="ephemeral")
    result = await invoke_with_fallback(prompt, TermGenerationOutput)
    out = result.output

    # Schema already validated by invoke_with_fallback; re-assert the
    # min/max-length cardinality contract the job relies on.
    assert isinstance(out, TermGenerationOutput)
    assert 2 <= len(out.paraphrases) <= 4
    assert 2 <= len(out.examples) <= 4
    assert _is_cefr(out.definition.cefr_level)
    assert all(_is_cefr(p.cefr_level) for p in out.paraphrases)
    assert all(_is_cefr(e.cefr_level) for e in out.examples)

    # Semantic-but-tolerant: the canonical meaning of "ephemeral" is about
    # short duration. Accept any model phrasing of that core sense.
    meaning = out.definition.canonical_meaning.lower()
    assert any(
        kw in meaning
        for kw in ("short", "brief", "transient", "fleeting", "temporary", "moment")
    ), f"canonical_meaning off-topic: {meaning!r}"

    # At least one example should actually use the term.
    assert any(
        "ephemeral" in e.value.lower() for e in out.examples
    ), "no example sentence used the target term"

    assert result.model_used  # a concrete model name, not empty
