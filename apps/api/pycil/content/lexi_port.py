"""Structural capabilities consumed from Lexi's public boundary."""

from collections.abc import Sequence
from typing import Protocol

from lexi_ai.contracts import (
    AnswerSubmission,
    Evaluation,
    PrepareDemand,
    PresentedQuestion,
    QuestionTypeInfo,
)


class SearchResultView(Protocol):
    display: str
    entry_type: str | None
    score: float
    lexi_word_id: int | None
    cambridge_id: int | None
    gloss: str | None


class SenseView(Protocol):
    definition: str
    tier: str
    pos: str | None
    cefr_level: str | None
    sense_id: int | None
    examples: list[str]


class EntryView(Protocol):
    word_id: int
    display: str
    norm: str
    status: str
    entry_type: str | None
    senses: list[SenseView]


class PrepareReportView(Protocol):
    produced: dict[tuple[int, int], int]


class LexiReader(Protocol):
    async def search(self, query: str) -> list[SearchResultView]: ...

    async def get_entry(self, word_id: int) -> EntryView | None: ...

    async def get_senses(self, sense_ids: list[int]) -> list[SenseView]: ...

    def question_types(self) -> list[QuestionTypeInfo]: ...

    async def get_question(self, question_id: int) -> PresentedQuestion | None: ...

    async def list_questions_for_sense(
        self, sense_id: int, type_id: str | None = None
    ) -> list[PresentedQuestion]: ...

    async def retrieve_question(
        self,
        sense_id: int,
        difficulty_level: int,
        excluded_ids: frozenset[int],
        type_id: str,
    ) -> PresentedQuestion | None: ...

    async def retrieve_exposure(self, sense_id: int) -> PresentedQuestion: ...

    async def evaluate_answer(
        self, question_id: int, submission: AnswerSubmission
    ) -> Evaluation | None: ...


class LexiWorkerEngine(Protocol):
    def question_types(self) -> list[QuestionTypeInfo]: ...

    async def prepare_questions(
        self, word_id: int, demands: Sequence[PrepareDemand]
    ) -> PrepareReportView: ...

    async def evaluate_answer(
        self, question_id: int, submission: AnswerSubmission
    ) -> Evaluation | None: ...

    async def generate(self, source: object | str) -> EntryView: ...

    async def generate_fenced(self, source: object | str) -> EntryView: ...
