"""Tests for shared-py question types."""
from __future__ import annotations

from shared.questions import (
    FillAnswerInput,
    FillData,
    FillInBlankQuestion,
    MCQData,
    MultipleChoiceQuestion,
    WriteAnswerInput,
    WriteData,
    WriteQuestion,
)


def test_write_data_validates() -> None:
    d = WriteData(
        prompt="Define ephemeral.",
        expected_answer="lasting briefly",
        alt_answers=["short-lived"],
        explanation="from Greek ephemeros",
    )
    assert d.expected_answer == "lasting briefly"
    assert d.alt_answers == ["short-lived"]


def test_write_check_answer_exact_and_alts() -> None:
    data = {
        "prompt": "Define ephemeral.",
        "expected_answer": "Lasting Briefly",
        "alt_answers": ["short-lived"],
    }
    correct = WriteQuestion.check_answer(data, {"user_answer": "lasting briefly"})
    assert correct.correct
    alt = WriteQuestion.check_answer(data, {"user_answer": "short-lived"})
    assert alt.correct
    wrong = WriteQuestion.check_answer(data, {"user_answer": "permanent"})
    assert not wrong.correct


def test_fill_data_validates() -> None:
    d = FillData(
        prompt="The ___ flower wilted by sundown.",
        expected_answer="ephemeral",
        sentence_id=42,
    )
    assert d.sentence_id == 42


def test_fill_check_answer() -> None:
    data = {
        "prompt": "The ___ flower wilted.",
        "expected_answer": "ephemeral",
        "alt_answers": ["ephemerals"],
    }
    ok = FillInBlankQuestion.check_answer(data, {"user_answer": "Ephemeral"})
    assert ok.correct
    bad = FillInBlankQuestion.check_answer(data, {"user_answer": "permanent"})
    assert not bad.correct


def test_mcq_check_answer_remains() -> None:
    data = {
        "stem": "What does ephemeral mean?",
        "options": ["short-lived", "permanent", "loud", "blue"],
        "correct_index": 0,
        "explanation": "Greek ephemeros = for a day",
        "distractor_rationale": ["wrong", "wrong", "wrong"],
    }
    out = MultipleChoiceQuestion.check_answer(data, {"selected_index": 0})
    assert out.correct


def test_mcq_data_options_unique() -> None:
    """MCQ data validates options shape."""
    valid = MCQData(
        stem="Pick the right answer.",
        options=["a", "b", "c", "d"],
        correct_index=1,
        explanation="b is right",
        distractor_rationale=["nope", "nope", "nope"],
    )
    assert valid.correct_index == 1


def test_input_models() -> None:
    """User-answer input shapes parse cleanly."""
    assert WriteAnswerInput(user_answer="hi").user_answer == "hi"
    assert FillAnswerInput(user_answer="word").user_answer == "word"
