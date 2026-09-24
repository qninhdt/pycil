"""Typed delivery payloads never expose Lexi grading material."""

from types import SimpleNamespace

import pytest
from lexi_ai.contracts import (
    Flashcard,
    FreeText,
    PresentedQuestion,
    RenderKind,
    SingleChoice,
    TextSpan,
)

from pycil.common.errors import ServiceUnavailableError
from pycil.learning.delivery import presentation_payload, render_format

_GRADING_KEYS = {"correct_index", "answer_norm", "accepted_forms", "rubric", "target_norm"}


def _question(render) -> PresentedQuestion:
    kind = {
        Flashcard: RenderKind.FLASHCARD,
        SingleChoice: RenderKind.SINGLE_CHOICE,
        TextSpan: RenderKind.TEXT_SPAN,
        FreeText: RenderKind.FREE_TEXT,
    }[type(render)]
    return PresentedQuestion(
        question_id=1,
        word_id=7,
        sense_id=8,
        type_id="test",
        render_kind=kind,
        difficulty_level=1,
        interaction="assessment",
        render=render,
    )


@pytest.mark.parametrize(
    ("render", "expected_format"),
    [
        (Flashcard(word="run", definition="move", pos="verb"), "flashcard"),
        (SingleChoice(stem="pick", options=("a", "b")), "single_choice"),
        (TextSpan(stem_with_blank="I ___", word_bank=("run",)), "text_span"),
        (FreeText(prompt="use it"), "free_text"),
    ],
)
def test_every_typed_render_is_answer_safe(render, expected_format):
    question = _question(render)
    delivered = presentation_payload(question)

    assert render_format(question) == expected_format
    assert not (set(delivered) & _GRADING_KEYS)


def test_untyped_render_fails_closed():
    question = SimpleNamespace(render=object())
    with pytest.raises(ServiceUnavailableError):
        presentation_payload(question)
