"""Tests for the thin public Lexi reader composition seam."""

from lexi_ai.contracts import PresentedQuestion, RenderKind, SingleChoice

from pycil.content import lexi_library


def _question() -> PresentedQuestion:
    return PresentedQuestion(
        question_id="13",
        word_id="7",
        sense_id="8",
        type_id="definition_mcq",
        difficulty_level=1,
        interaction="assessment",
        render=SingleChoice(stem="Choose", options=("a", "b")),
    )


def test_create_lexicon_reader_uses_public_reader_facade():
    reader = object()

    class Lexicon:
        def reader(self):
            return reader

    assert lexi_library.create_lexicon_reader(Lexicon()) is reader


def test_create_embedded_reader_uses_public_factory(monkeypatch):
    reader = object()

    class Lexicon:
        @classmethod
        def from_settings(cls):
            return cls()

        def reader(self):
            return reader

    monkeypatch.setattr(lexi_library, "Lexicon", Lexicon)
    lexicon, constructed_reader = lexi_library.create_embedded_lexicon_reader()

    assert isinstance(lexicon, Lexicon)
    assert constructed_reader is reader


def test_released_question_contract_is_answer_safe():
    question = _question()

    assert question.question_id == "13"
    assert isinstance(question.render, SingleChoice)
    assert question.render.options == ("a", "b")
    assert not hasattr(question.render, "correct_index")
    assert RenderKind.SINGLE_CHOICE.value == "single_choice"
