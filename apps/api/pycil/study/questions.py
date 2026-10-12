"""Build public runtime exercises from persisted artifacts without inference."""

import random

from lexi_ai import QuestionType, TargetPlacement
from lexi_ai.text import answer_key
from lexi_ai.vocab import INFLECTION_CODES

from pycil.http import Problem
from pycil.study.schemas import Option, PreparedQuestion, Question

randomness = random.SystemRandom()


def tagged(expression, sense):
    inflection = next(
        (form.inf for form in sense.forms if answer_key(form.surface) == answer_key(expression)),
        None,
    )
    code = next((code for code, inf in INFLECTION_CODES.items() if inf == inflection), "")
    return f"[{expression}{'|' + code if code else ''}]"


def build_question(artifact, question_type, fmt, sense, lemma, config):
    payload = artifact.payload
    count = config.generation.distractor_count
    placement = None
    if question_type in {QuestionType.DEFINITION_TO_WORD, QuestionType.WORD_TO_DEFINITION}:
        definition = randomness.choice(payload["corrects"])
        pairs = randomness.sample(payload["distractors"], min(count, len(payload["distractors"])))
        if question_type == QuestionType.DEFINITION_TO_WORD:
            content, correct, wrong = definition, lemma, [p["word"] for p in pairs]
        else:
            content, correct, wrong = f"[{lemma}]", definition, [p["definition"] for p in pairs]
    elif question_type == QuestionType.WORD_TO_USAGE:
        content = f"[{lemma}] — {sense.definition.content}"
        correct = randomness.choice(payload["corrects"])
        wrong = randomness.sample(payload["distractors"], min(count, len(payload["distractors"])))
    elif question_type == QuestionType.CONTEXT_TO_WORD:
        content, correct, wrong = payload["context"], lemma, payload["distractors"]
    elif question_type in {QuestionType.CLOZE_TO_WORD, QuestionType.MEANING_IN_CONTEXT}:
        pair = payload["correct"]
        if question_type == QuestionType.CLOZE_TO_WORD:
            content, correct = payload["context"], pair["expression"]
            wrong = [p["expression"] for p in payload["distractors"]]
        else:
            content = payload["context"].replace("_", tagged(pair["expression"], sense))
            correct, wrong = pair["meaning"], [p["meaning"] for p in payload["distractors"]]
    elif question_type == QuestionType.DIALOGUE_COMPLETION:
        point = randomness.choice(payload["completion_points"])
        index = point["turn_index"]
        turns = [
            dict(speaker=next(iter(t)), text=next(iter(t.values())))
            for t in payload["conversation"]
        ]
        correct, wrong = turns[index]["text"], point["distractors"]
        placement = TargetPlacement.OPTIONS if "[" in correct else TargetPlacement.DIALOGUE
        turns[index]["text"] = None
        content = turns
    elif question_type == QuestionType.SENTENCE_REWRITE:
        content = f"[{lemma}]\n{payload['source']}"
        correct, wrong = payload["correct"], payload["distractors"]
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
        level=config.learning.pair_levels[question_type][fmt],
        options=options,
    )
