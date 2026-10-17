"""Build public runtime exercises from persisted artifacts without inference."""

import random

from pycil.study.artifacts.schemas import (
    ARTIFACT_SCHEMAS,
    Artifact,
    ContextToWordArtifact,
    ContextWordMeaningArtifact,
    DialogueArtifact,
    UsageArtifact,
    WordDefinitionArtifact,
)
from pycil.study.config import StudyConfig
from pycil.study.enums import QUESTION_ARTIFACT_MAP, QuestionType, ResponseFormat, TargetPlacement
from pycil.study.models import QuestionArtifact
from pycil.study.schemas import DialogueTurn, Option, PreparedQuestion, Question
from pycil.utils.errors import Conflict
from pycil.vocabulary.enums import INFLECTION_CODES
from pycil.vocabulary.schemas import Sense
from pycil.vocabulary.text import answer_key

randomness = random.SystemRandom()


def tagged(expression: str, sense: Sense) -> str:
    inflection = next(
        (form.inf for form in sense.forms if answer_key(form.surface) == answer_key(expression)),
        None,
    )
    code = next((code for code, inf in INFLECTION_CODES.items() if inf == inflection), "")
    return f"[{expression}{'|' + code if code else ''}]"


def build_question(
    artifact: Artifact | QuestionArtifact,
    question_type: QuestionType,
    fmt: ResponseFormat,
    sense: Sense,
    lemma: str,
    policy: StudyConfig,
) -> PreparedQuestion:
    try:
        payload_model = (
            artifact.typed_payload
            if isinstance(artifact, Artifact)
            else ARTIFACT_SCHEMAS[QUESTION_ARTIFACT_MAP[question_type]].model_validate(
                artifact.payload
            )
        )
    except Exception:
        raise Conflict("artifact_bank_incomplete") from None
    count = policy.artifacts.distractor_count
    placement: TargetPlacement | None = None
    content: str | list[DialogueTurn]
    correct: str
    wrong: list[str]

    if isinstance(payload_model, WordDefinitionArtifact):
        definition = randomness.choice(payload_model.corrects)
        pairs = randomness.sample(
            payload_model.distractors, min(count, len(payload_model.distractors))
        )
        if question_type == QuestionType.DEFINITION_TO_WORD:
            content, correct, wrong = definition, lemma, [p.word for p in pairs]
        else:
            content, correct, wrong = f"[{lemma}]", definition, [p.definition for p in pairs]
    elif isinstance(payload_model, UsageArtifact):
        if sense.definition is None:
            raise Conflict("artifact_bank_incomplete")
        content = f"[{lemma}] — {sense.definition.content}"
        correct = randomness.choice(payload_model.corrects)
        wrong = randomness.sample(
            payload_model.distractors, min(count, len(payload_model.distractors))
        )
    elif isinstance(payload_model, ContextToWordArtifact):
        content = payload_model.context
        correct = lemma
        wrong = payload_model.distractors
    elif isinstance(payload_model, ContextWordMeaningArtifact):
        if question_type == QuestionType.CLOZE_TO_WORD:
            content = payload_model.context
            correct = payload_model.correct.expression
            wrong = [p.expression for p in payload_model.distractors]
        else:
            tagged_expr = tagged(payload_model.correct.expression, sense)
            content = payload_model.context.replace("_", tagged_expr)
            correct = payload_model.correct.meaning
            wrong = [p.meaning for p in payload_model.distractors]
    elif isinstance(payload_model, DialogueArtifact):
        point = randomness.choice(payload_model.completion_points)
        turns = [
            DialogueTurn(speaker=next(iter(t)), text=next(iter(t.values())))
            for t in payload_model.conversation
        ]
        correct = turns[point.turn_index].text or ""
        wrong = point.distractors
        placement = TargetPlacement.OPTIONS if "[" in correct else TargetPlacement.DIALOGUE
        turns[point.turn_index].text = None
        content = turns
    else:
        content = f"[{lemma}]\n{payload_model.source}"
        correct = payload_model.correct
        wrong = payload_model.distractors
    if not wrong:
        raise Conflict("artifact_bank_incomplete")
    correct_option = Option(id="correct", content=correct)
    distractors = [
        Option(id=f"distractor-{index}", content=text) for index, text in enumerate(wrong)
    ]
    options = [correct_option, *distractors]
    randomness.shuffle(options)
    return PreparedQuestion(
        question=Question(
            question_artifact_id=artifact.id,
            sense_id=sense.id,
            question_type=question_type,
            content=content,
            correct=correct_option,
            distractors=distractors,
            target_placement=placement,
        ),
        format=fmt,
        level=policy.pair_levels[question_type][fmt],
        options=options,
    )
