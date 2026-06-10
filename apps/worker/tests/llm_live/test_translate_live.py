"""Live contract: definition translation against a real model.

Proves the translate.md prompt + TranslationOutput schema + json_mode parse
path round-trips through a live model and returns a non-empty translation in
the target language. Skipped unless RUN_LLM_LIVE=1 (see conftest).
"""
from __future__ import annotations

import pytest

from worker.jobs.translate_definition import TranslationOutput
from worker.llm.openrouter import generate_with_schema
from worker.prompts import render

pytestmark = pytest.mark.llm_live


async def test_translate_definition_live() -> None:
    prompt = render(
        "translate.md",
        term_value="ephemeral",
        canonical_meaning="lasting for a very short time; transient",
        target_lang="vi",
    )
    out = await generate_with_schema(prompt, TranslationOutput)

    assert isinstance(out, TranslationOutput)
    # A real translation is non-empty and not a verbatim echo of the English.
    translated = out.canonical_translated.strip()
    assert translated
    assert translated.lower() != "lasting for a very short time; transient"
