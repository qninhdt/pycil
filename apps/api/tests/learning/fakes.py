"""Deterministic fakes for Lexi's public answer-safe contract."""

from dataclasses import dataclass

from lexi_ai.contracts import (
    AnswerSubmission,
    ChoiceResponse,
    ChoiceReveal,
    Evaluation,
    Flashcard,
    FreeText,
    PresentedQuestion,
    QuestionTypeInfo,
    RenderKind,
    SingleChoice,
    SpanReveal,
    TextResponse,
    TextSpan,
)

SHIPPED_TYPES = [
    QuestionTypeInfo("flashcard", RenderKind.FLASHCARD, "exposure", frozenset({0})),
    QuestionTypeInfo("definition_mcq", RenderKind.SINGLE_CHOICE, "assessment", frozenset({1})),
    QuestionTypeInfo("contextual_mcq", RenderKind.SINGLE_CHOICE, "assessment", frozenset({1, 2})),
    QuestionTypeInfo("cloze", RenderKind.TEXT_SPAN, "assessment", frozenset({2, 3})),
    QuestionTypeInfo("use_in_sentence", RenderKind.FREE_TEXT, "assessment", frozenset({3, 4})),
]
SHIPPED_DESCRIPTORS = SHIPPED_TYPES

# A rubric-graded type declared across the whole assessment ladder.
#
# The shipped set cannot reach the deferred/LLM branch of `submit_answer` at the
# level a session actually requests: `use_in_sentence` is the only free-text type
# and it declares levels {3, 4}, while acquisition always requests
# `ASSESSMENT_FLOOR` (1) and the resolver only ever walks *down* from the requested
# level. So every question the suite could obtain graded synchronously, and 143
# lines of `submit_answer` were unreachable from a test.
#
# Registered as a separate descriptor set rather than by widening
# `use_in_sentence`, so the default fake keeps describing the shipped contract
# exactly and only tests that opt in see a rubric type at level 1.
RUBRIC_AT_EVERY_LEVEL = [
    QuestionTypeInfo("flashcard", RenderKind.FLASHCARD, "exposure", frozenset({0})),
    QuestionTypeInfo(
        "rubric_free_text",
        RenderKind.FREE_TEXT,
        "assessment",
        frozenset({1, 2, 3, 4}),
    ),
]

_RENDER_BY_TYPE = {item.type_id: item.render_kind for item in SHIPPED_TYPES}
_RENDER_BY_TYPE.update(
    {item.type_id: item.render_kind for item in RUBRIC_AT_EVERY_LEVEL}
)
# Types whose verdict comes from a model rather than a rule, so `evaluate_answer`
# reports `pending` and the route must defer to the worker.
_LLM_TYPES = {"use_in_sentence", "rubric_free_text"}


@dataclass(frozen=True)
class FakePrepareReport:
    produced: dict[tuple[int, int], int]


def _render(kind: RenderKind):
    if kind is RenderKind.SINGLE_CHOICE:
        return SingleChoice(stem="pick", options=("a", "b"))
    if kind is RenderKind.TEXT_SPAN:
        return TextSpan(stem_with_blank="I ___", word_bank=("run", "sit"))
    if kind is RenderKind.FREE_TEXT:
        return FreeText(prompt="use it")
    return Flashcard(word="run", pos="verb", definition="to move fast")


def _answer_text(submission: AnswerSubmission) -> str:
    response = submission.response
    if isinstance(response, TextResponse):
        return response.text
    if isinstance(response, ChoiceResponse):
        return str(response.selected_index)
    return ""


class FakeLexiReader:
    def __init__(self, word_id: int = 7, types: list[QuestionTypeInfo] | None = None) -> None:
        self.word_id = word_id
        # Defaults to the shipped contract; a test that needs a rubric type at a
        # level a session actually requests passes `RUBRIC_AT_EVERY_LEVEL`.
        self._types = list(types) if types is not None else list(SHIPPED_TYPES)
        self._next_qid = 1000
        self._supply: dict[tuple[int, int, str], list[int]] = {}
        self._questions: dict[int, PresentedQuestion] = {}
        self._answers: dict[int, str] = {}

    def add_supply(self, sense_id: int, level: int, type_id: str, count: int = 1) -> list[int]:
        ids: list[int] = []
        for _ in range(count):
            qid = self._next_qid
            self._next_qid += 1
            kind = _RENDER_BY_TYPE[type_id]
            question = PresentedQuestion(
                question_id=str(qid),
                word_id=str(self.word_id),
                sense_id=str(sense_id),
                type_id=type_id,
                difficulty_level=level,
                interaction="assessment",
                render=_render(kind),
            )
            self._questions[qid] = question
            self._answers[qid] = "a" if kind is RenderKind.SINGLE_CHOICE else "run"
            self._supply.setdefault((sense_id, level, type_id), []).append(qid)
            ids.append(qid)
        return ids

    def question_types(self) -> list[QuestionTypeInfo]:
        return list(self._types)

    async def get_question(self, question_id: int) -> PresentedQuestion | None:
        return self._questions.get(question_id)

    async def list_questions_for_sense(self, sense_id, type_id=None):
        return [q for q in self._questions.values() if q.sense_id == str(sense_id)]

    async def retrieve_question(self, sense_id, difficulty_level, excluded_ids, type_id):
        for qid in self._supply.get((sense_id, difficulty_level, type_id), []):
            if qid not in excluded_ids:
                return self._questions[qid]
        return None

    async def retrieve_exposure(self, sense_id: int) -> PresentedQuestion:
        return PresentedQuestion(
            question_id=f"exposure:{sense_id}",
            word_id=str(self.word_id),
            sense_id=str(sense_id),
            type_id="flashcard",
            difficulty_level=0,
            interaction="exposure",
            render=_render(RenderKind.FLASHCARD),
        )

    async def evaluate_answer(
        self, question_id: int, submission: AnswerSubmission
    ) -> Evaluation | None:
        question = self._questions.get(question_id)
        if question is None:
            return None
        if question.type_id in _LLM_TYPES:
            return Evaluation(question_id=str(question_id), status="pending")
        correct = _answer_text(submission) == self._answers.get(question_id)
        reveal = (
            ChoiceReveal(correct_index=0, correct_option="a")
            if isinstance(question.render, SingleChoice)
            else SpanReveal(correct_answer="run")
        )
        return Evaluation(
            question_id=str(question_id),
            status="graded",
            correct=correct,
            score=1.0 if correct else 0.0,
            reveal=reveal,
        )

    async def search(self, query):
        return []

    async def get_entry(self, word_id):
        return None

    async def get_senses(self, sense_ids):
        return []


class FakeLexiWorkerEngine:
    def __init__(self, reader: FakeLexiReader, judge_correct: bool = True) -> None:
        self._reader = reader
        self.judge_correct = judge_correct
        self.prepared: list[tuple[int, str, int, int]] = []

    def question_types(self) -> list[QuestionTypeInfo]:
        return list(SHIPPED_TYPES)

    async def prepare_questions(self, word_id: int, demands) -> FakePrepareReport:
        produced: dict[tuple[int, int], int] = {}
        for demand in demands:
            sense_id = int(demand.sense_id)
            self.prepared.append(
                (
                    word_id,
                    demand.sense_id,
                    demand.difficulty_level,
                    demand.expected_count,
                )
            )
            self._reader.add_supply(
                sense_id,
                demand.difficulty_level,
                _type_for_level(demand.difficulty_level),
                demand.expected_count,
            )
            produced[(sense_id, demand.difficulty_level)] = demand.expected_count
        return FakePrepareReport(produced)

    async def evaluate_answer(self, question_id: int, submission: AnswerSubmission):
        if await self._reader.get_question(question_id) is None:
            return None
        return Evaluation(
            question_id=str(question_id),
            status="graded",
            correct=self.judge_correct,
            score=1.0 if self.judge_correct else 0.0,
            feedback="judged",
        )


def _type_for_level(level: int) -> str:
    for info in SHIPPED_TYPES:
        if info.interaction == "assessment" and level in info.difficulty_levels:
            return info.type_id
    return "definition_mcq"
