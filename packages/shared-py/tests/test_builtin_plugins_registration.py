"""Builtin plugin registration + grading-mode routing + answer-stripping.

Pins the Phase 1 migration invariants: the three builtin types self-register,
sync/async grading is driven by ``requires_server_grading``, and
``public_projection`` strips answer fields for every builtin type.
"""
from __future__ import annotations

import shared.questions  # noqa: F401  (self-registers builtin plugins)
from shared.questions import registry


def test_three_builtins_registered() -> None:
    assert sorted(registry.all_types()) == [
        "FILL_IN_BLANK",
        "MULTIPLE_CHOICE",
        "WRITE",
    ]


def test_grading_mode_routing() -> None:
    # WRITE needs the async LLM-judge tier; MCQ + FILL grade synchronously.
    assert registry.get("WRITE").requires_server_grading is True
    assert registry.get("MULTIPLE_CHOICE").requires_server_grading is False
    assert registry.get("FILL_IN_BLANK").requires_server_grading is False


def test_no_dead_grading_strategy_field() -> None:
    # The grading-strategy registry was dropped; no dangling field should
    # reference a missing module.
    assert not hasattr(registry.get("MULTIPLE_CHOICE"), "grading_strategy")


def test_public_projection_strips_mcq_answer_fields() -> None:
    data = {
        "stem": "q",
        "options": ["a", "b", "c", "d"],
        "correct_index": 2,
        "explanation": "because",
        "distractor_rationale": ["x", "y", "z"],
    }
    pub = registry.get("MULTIPLE_CHOICE").public_projection(data)
    assert "correct_index" not in pub
    assert "explanation" not in pub
    assert "distractor_rationale" not in pub
    assert pub["stem"] == "q" and len(pub["options"]) == 4


def test_public_projection_strips_write_answer_fields() -> None:
    data = {
        "prompt": "define cat",
        "expected_answer": "a feline",
        "alt_answers": ["feline"],
        "explanation": "note",
    }
    pub = registry.get("WRITE").public_projection(data)
    assert "expected_answer" not in pub
    assert "alt_answers" not in pub
    assert "explanation" not in pub
    assert pub["prompt"] == "define cat"


def test_public_projection_strips_fill_answer_fields() -> None:
    data = {
        "prompt": "the cat is ___",
        "expected_answer": "black",
        "alt_answers": [],
        "explanation": "color",
    }
    pub = registry.get("FILL_IN_BLANK").public_projection(data)
    assert "expected_answer" not in pub
    assert "alt_answers" not in pub
    assert pub["prompt"].endswith("___")
