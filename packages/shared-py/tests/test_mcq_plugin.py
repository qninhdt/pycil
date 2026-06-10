"""MCQ plugin behaviour, resolved through the registry (Task 2)."""
from __future__ import annotations

import shared.questions  # noqa: F401  (triggers builtin registration)
from shared.questions import registry
from shared.questions.plugins.multiple_choice import MCQData

_DATA = {
    "stem": "What does ephemeral mean?",
    "options": ["short-lived", "permanent", "loud", "blue"],
    "correct_index": 0,
    "explanation": "Greek ephemeros = for a day",
    "distractor_rationale": ["wrong", "wrong", "wrong"],
}


def test_mcq_registered() -> None:
    assert registry.is_registered("MULTIPLE_CHOICE")
    plugin = registry.get("MULTIPLE_CHOICE")
    assert plugin.type_id == "MULTIPLE_CHOICE"
    assert plugin.requires_server_grading is False
    assert plugin.data_schema is MCQData


def test_mcq_check_answer_correct() -> None:
    plugin = registry.get("MULTIPLE_CHOICE")
    res = plugin.check_answer(_DATA, {"selected_index": 0})
    assert res.correct
    assert res.score == 1.0
    assert res.reveal["correct_index"] == 0
    assert res.feedback == "Greek ephemeros = for a day"


def test_mcq_check_answer_wrong() -> None:
    plugin = registry.get("MULTIPLE_CHOICE")
    res = plugin.check_answer(_DATA, {"selected_index": 2})
    assert not res.correct
    assert res.score == 0.0
    assert res.reveal["correct_index"] == 0


def test_mcq_check_answer_invalid() -> None:
    plugin = registry.get("MULTIPLE_CHOICE")
    res = plugin.check_answer(_DATA, {"selected_index": "x"})
    assert not res.correct
    assert res.feedback == "invalid_selected_index"


def test_mcq_public_projection_hides_answer() -> None:
    plugin = registry.get("MULTIPLE_CHOICE")
    pub = plugin.public_projection(_DATA)
    assert "stem" in pub
    assert "options" in pub
    assert "correct_index" not in pub
    assert "explanation" not in pub
    assert "distractor_rationale" not in pub


def test_mcq_sanitize_strips_urls() -> None:
    plugin = registry.get("MULTIPLE_CHOICE")
    out = MCQData(
        stem="Visit http://evil.test now to learn",
        options=["a", "b", "c", "d"],
        correct_index=1,
        explanation="see http://x.test for more",
        distractor_rationale=["n1", "n2", "n3"],
    )
    clean = plugin.sanitize(out)
    assert "http" not in clean["stem"]
    assert "http" not in clean["explanation"]
    assert clean["correct_index"] == 1


def test_mcq_prompt_inputs() -> None:
    plugin = registry.get("MULTIPLE_CHOICE")
    inputs = plugin.prompt_inputs(
        {"term_value": "ephemeral", "cefr_level": "B2"}, "easy"
    )
    assert inputs["term_value"] == "ephemeral"
    assert inputs["difficulty"] == "easy"
    assert plugin.template_name() == "mcq.md"
