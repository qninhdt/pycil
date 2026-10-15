"""Build public runtime exercises from persisted artifacts without inference."""

import random
from typing import cast

from pycil.app.config import AppConfig
from pycil.app.http import Problem
from pycil.study.artifacts.schemas import Artifact
from pycil.study.enums import QuestionType, ResponseFormat, TargetPlacement
from pycil.study.models import QuestionArtifact
from pycil.study.schemas import DialogueTurn, Option, PreparedQuestion, Question
from pycil.study.types import CompletionPointDict
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
    config: AppConfig,
) -> PreparedQuestion:
    payload = cast(dict[str, object], artifact.payload)
    count = config.product.study.artifacts.distractor_count
    placement: TargetPlacement | None = None
    content: str | list[DialogueTurn]
    correct: str
    wrong: list[str]

    if question_type in {QuestionType.DEFINITION_TO_WORD, QuestionType.WORD_TO_DEFINITION}:
        corrects = cast(list[str], payload["corrects"])
        distractors = cast(list[dict[str, str]], payload["distractors"])
        definition = randomness.choice(corrects)
        pairs = randomness.sample(distractors, min(count, len(distractors)))
        if question_type == QuestionType.DEFINITION_TO_WORD:
            content, correct, wrong = definition, lemma, [p["word"] for p in pairs]
        else:
            content, correct, wrong = f"[{lemma}]", definition, [p["definition"] for p in pairs]
    elif question_type == QuestionType.WORD_TO_USAGE:
        if sense.definition is None:
            raise Problem(409, "artifact_bank_incomplete")
        content = f"[{lemma}] — {sense.definition.content}"
        correct = randomness.choice(cast(list[str], payload["corrects"]))
        distractors = cast(list[str], payload["distractors"])
        wrong = randomness.sample(distractors, min(count, len(distractors)))
    elif question_type == QuestionType.CONTEXT_TO_WORD:
        content = cast(str, payload["context"])
        correct = lemma
        wrong = cast(list[str], payload["distractors"])
    elif question_type in {QuestionType.CLOZE_TO_WORD, QuestionType.MEANING_IN_CONTEXT}:
        pair = cast(dict[str, str], payload["correct"])
        distractor_pairs = cast(list[dict[str, str]], payload["distractors"])
        if question_type == QuestionType.CLOZE_TO_WORD:
            content = cast(str, payload["context"])
            correct = pair["expression"]
            wrong = [p["expression"] for p in distractor_pairs]
        else:
            content = cast(str, payload["context"]).replace("_", tagged(pair["expression"], sense))
            correct = pair["meaning"]
            wrong = [p["meaning"] for p in distractor_pairs]
    elif question_type == QuestionType.DIALOGUE_COMPLETION:
        points = cast(list[CompletionPointDict], payload["completion_points"])
        point = randomness.choice(points)
        index = point["turn_index"]
        raw_conversation = cast(list[dict[str, str | None]], payload["conversation"])
        turns = [
            DialogueTurn(speaker=next(iter(t)), text=next(iter(t.values())))
            for t in raw_conversation
        ]
        correct = turns[index].text or ""
        wrong = point["distractors"]
        placement = TargetPlacement.OPTIONS if "[" in correct else TargetPlacement.DIALOGUE
        turns[index].text = None
        content = turns
    elif question_type == QuestionType.SENTENCE_REWRITE:
        content = f"[{lemma}]\n{payload['source']}"
        correct = cast(str, payload["correct"])
        wrong = cast(list[str], payload["distractors"])
    else:
        raise Problem(422, "unsupported_question_type")
    if not wrong:
        raise Problem(409, "artifact_bank_incomplete")
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
        level=config.product.study.pair_levels[question_type][fmt],
        options=options,
    )
