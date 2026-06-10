"""Live contract: MCQ generation against a real model.

Proves the mcq.md prompt + the MULTIPLE_CHOICE plugin's MCQData schema +
json_mode parse path round-trips through a live model and yields a usable,
gradable question. Skipped unless RUN_LLM_LIVE=1 (see conftest).
"""
from __future__ import annotations

import pytest

from shared.questions import registry

from worker.llm.openrouter import invoke_with_fallback
from worker.prompts import render

pytestmark = pytest.mark.llm_live


async def test_generate_mcq_live_structure_and_gradability() -> None:
    plugin = registry.get("MULTIPLE_CHOICE")
    inputs = {
        "term_value": "ephemeral",
        "part_of_speech": "ADJECTIVE",
        "cefr_level": "B2",
        "canonical_meaning": "Lasting for a very short time; transient.",
        "paraphrase_sample": "Something that does not last long.",
        "example_sample": "The joy of a new purchase is often ephemeral.",
    }
    prompt = render(plugin.template_name(), **plugin.prompt_inputs(inputs, "easy"))
    result = await invoke_with_fallback(prompt, plugin.data_schema)
    out = result.output

    # Schema (MCQData) already enforces 4 unique options, correct_index 0..3,
    # 3 distractor rationales — re-assert the load-bearing pieces explicitly.
    assert len(out.options) == 4
    assert len({o.strip().lower() for o in out.options}) == 4
    assert 0 <= out.correct_index <= 3
    assert len(out.distractor_rationale) == 3
    assert out.stem.strip()

    # The plugin must be able to grade its own correct answer as correct.
    data = plugin.sanitize(out)
    check = plugin.check_answer(data, {"selected_index": out.correct_index})
    assert check.correct is True
    assert check.score == 1.0

    # A different option must grade as incorrect (sanity that grading discriminates).
    wrong = (out.correct_index + 1) % 4
    assert plugin.check_answer(data, {"selected_index": wrong}).correct is False
