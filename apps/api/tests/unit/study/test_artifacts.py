import copy
import random
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pycil.app.config import load_config
from pycil.study import questions
from pycil.study.artifacts.schemas import ARTIFACT_SCHEMAS, validate_artifact
from pycil.study.enums import (
    ALLOWED_PAIRS,
    QUESTION_ARTIFACT_MAP,
    QuestionType,
    ResponseFormat,
    TargetPlacement,
)
from pycil.study.enums import QuestionArtifactType as Kind
from pycil.utils.errors import OperationError
from pycil.vocabulary.errors import InvalidOutputError
from tests.support.artifacts import lexical_target, payloads


@pytest.mark.parametrize("kind", list(Kind))
def test_each_artifact_type_accepts_complete_licensed_payload(kind):
    word, sense = lexical_target()
    payload = ARTIFACT_SCHEMAS[kind].model_validate(payloads()[kind])
    validate_artifact(payload, kind, word, sense, 1, 1)


@pytest.mark.parametrize(
    "kind, field, value",
    [
        (Kind.WORD_DEFINITION, "distractors", [{"word": "lender", "definition": "different"}]),
        (Kind.WORD_DEFINITION, "corrects", [" A PLACE TO BUY GOODS "]),
        (Kind.WORD_TO_USAGE, "corrects", ["The bank holds deposits."]),
        (Kind.WORD_TO_USAGE, "distractors", ["The [lender] holds deposits.", "extra"]),
        (Kind.CONTEXT_WORD_MEANING, "context", "The bank is _."),
        (Kind.CONTEXT_WORD_MEANING, "context", "There are __."),
        (Kind.CONTEXT_WORD_MEANING, "correct", {"expression": "shop", "meaning": "a retailer"}),
        (Kind.CONTEXT_TO_WORD, "context", "Find the [bank]."),
        (Kind.CONTEXT_TO_WORD, "context", "Deposit money at _."),
        (Kind.CONTEXT_TO_WORD, "distractors", ["lender"]),
        (Kind.SENTENCE_REWRITE, "source", "She visits banks."),
        (Kind.SENTENCE_REWRITE, "correct", "She put money in the [shop]."),
        (Kind.DIALOGUE_COMPLETION, "conversation", [{"A": "No target."}] * 4),
        (Kind.DIALOGUE_COMPLETION, "conversation", [{"A": "[bank]"}] * 4),
    ],
)
def test_artifact_semantic_defects_are_rejected(kind, field, value):
    word, sense = lexical_target()
    data = payloads()[kind] | {field: value}
    payload = ARTIFACT_SCHEMAS[kind].model_validate(data)
    with pytest.raises(InvalidOutputError):
        validate_artifact(payload, kind, word, sense, 1, 1)


@pytest.mark.parametrize(
    "points",
    [[{"turn_index": 4, "distractors": ["x"]}], [{"turn_index": 1, "distractors": ["x"]}] * 2],
)
def test_dialogue_completion_indices_must_be_unique_and_in_range(points):
    with pytest.raises(ValidationError):
        ARTIFACT_SCHEMAS[Kind.DIALOGUE_COMPLETION].model_validate(
            payloads()[Kind.DIALOGUE_COMPLETION] | {"completion_points": points}
        )


def test_dialogue_speaker_shape_and_replacement_target_are_validated():
    word, sense = lexical_target()
    data = payloads()[Kind.DIALOGUE_COMPLETION]
    with pytest.raises(ValidationError):
        ARTIFACT_SCHEMAS[Kind.DIALOGUE_COMPLETION].model_validate(
            data | {"conversation": [{"A": "x", "B": "y"}] * 4}
        )
    data["completion_points"] = [{"turn_index": 0, "distractors": ["The [bank] closes."]}]
    with pytest.raises(InvalidOutputError):
        validate_artifact(
            ARTIFACT_SCHEMAS[Kind.DIALOGUE_COMPLETION].model_validate(data),
            Kind.DIALOGUE_COMPLETION,
            word,
            sense,
            1,
            1,
        )


@pytest.mark.parametrize("kind, fmt", sorted(ALLOWED_PAIRS))
def test_runtime_questions_map_answers_and_identity_for_supported_pairs(monkeypatch, kind, fmt):
    monkeypatch.setattr(questions, "randomness", random.Random(7))
    word, sense = lexical_target()
    data = payloads()[QUESTION_ARTIFACT_MAP[kind]]
    artifact = SimpleNamespace(id=42, payload=copy.deepcopy(data))
    built = questions.build_question(
        artifact, kind, fmt, sense, word.lemma, load_config().study
    )
    assert built.format is fmt
    assert built.question.question_artifact_id == 42
    assert built.question.sense_id == sense.id
    assert built.question.question_type is kind
    assert {option.id for option in built.options} == {"correct", "distractor-0"}
    assert built.question.correct in built.options
    assert built.question.distractors[0] in built.options
    if kind is QuestionType.MEANING_IN_CONTEXT:
        assert built.question.content == "She deposited money at the [banks|pl]."
        assert built.question.correct.content == "financial institutions"
    elif kind is QuestionType.CLOZE_TO_WORD:
        assert built.question.correct.content == "banks"
        assert "_" in built.question.content
    elif kind is QuestionType.DIALOGUE_COMPLETION:
        assert built.question.content[1].text is None
        assert built.question.target_placement is TargetPlacement.OPTIONS
        assert artifact.payload == data
    elif kind is QuestionType.DEFINITION_TO_WORD:
        assert built.question.correct.content == "bank"
    elif kind is QuestionType.WORD_TO_DEFINITION:
        assert built.question.correct.content == "a financial institution"


def test_dialogue_blank_outside_target_preserves_target_in_dialogue():
    word, sense = lexical_target()
    data = payloads()[Kind.DIALOGUE_COMPLETION]
    data["completion_points"] = [{"turn_index": 0, "distractors": ["Hello there."]}]
    built = questions.build_question(
        SimpleNamespace(id=42, payload=data),
        QuestionType.DIALOGUE_COMPLETION,
        ResponseFormat.SINGLE_CHOICE,
        sense,
        word.lemma,
        load_config().study,
    )
    assert built.question.content[0].text is None
    assert built.question.content[1].text == "At the [bank]."
    assert built.question.target_placement is TargetPlacement.DIALOGUE


def test_runtime_questions_reject_empty_bank():
    word, sense = lexical_target()
    with pytest.raises(OperationError) as error:
        questions.build_question(
            SimpleNamespace(id=42, payload={"context": "Deposit money.", "distractors": []}),
            QuestionType.CONTEXT_TO_WORD,
            ResponseFormat.SINGLE_CHOICE,
            sense,
            word.lemma,
            load_config().study,
        )
    assert error.value.code == "artifact_bank_incomplete"
