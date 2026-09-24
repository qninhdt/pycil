"""Structural capabilities consumed from Lexi's public boundary."""

from collections.abc import Sequence
from typing import Protocol

from lexi_ai.contracts import (
    AnswerSubmission,
    Evaluation,
    PrepareDemand,
    PresentedQuestion,
    QuestionTypeInfo,
    Reveal,
    TextResponse,
)

# Re-exported so `learning/domain` can name these types without importing an
# external library. The port owns which operations pycil may perform AND which
# vocabulary it states them in; a domain module reaching past it for the second
# had a direct dependency on lexi-ai's package layout, which is the coupling the
# port exists to absorb. An import-linter contract forbids the direct edge now.
#
# Application-layer modules may still import `lexi_ai.contracts` themselves: a
# stable published contracts package is a reasonable dependency one layer up.
# Domain is where it is not.
__all__ = [
    "AnswerSubmission",
    "Evaluation",
    "EntryView",
    "LexiReader",
    "LexiWorkerEngine",
    "PrepareDemand",
    "PrepareReportView",
    "PresentedQuestion",
    "QuestionTypeInfo",
    "Reveal",
    "SearchResultView",
    "SenseFormView",
    "SenseReferenceView",
    "SenseRelationView",
    "SenseView",
    "TextResponse",
]


class SearchResultView(Protocol):
    display: str
    entry_type: str | None
    score: float
    lexi_word_id: int | None
    cambridge_id: int | None
    gloss: str | None


class SenseFormView(Protocol):
    inf: str
    surface: str


class SenseReferenceView(Protocol):
    source: str
    source_ref: str


class SenseRelationView(Protocol):
    rel_type: str
    to_word_display: str
    to_word_id: int
    to_word_status: str
    wsd_state: str
    to_sense_id: int | None
    to_sense_gloss: str | None


class SenseView(Protocol):
    definition: str
    tier: str
    pos: str | None
    cefr_level: str | None
    sense_id: int | None
    examples: list[str]
    # The headword this sense belongs to. Derived by Lexi as ``render(norm)``, so it
    # is neutral even under a themed read. Optional because a view synthesized with
    # no word in scope leaves it None.
    word: str | None
    word_id: int | None
    # Full lexical record — surfaced only by the single-sense read. Deck and search
    # listings deliberately do not carry these.
    ipa_uk: str | None
    ipa_us: str | None
    guideword: str | None
    grammar: list[str]
    register: str | None
    connotation: str | None
    collocations: list[str]
    domain: str | None
    usage_note: str | None
    forms: list[SenseFormView]
    references: list[SenseReferenceView]
    relations: list[SenseRelationView]


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

    async def word_id_for(self, sense_id: int) -> int | None: ...

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
    async def prepare_questions(
        self, word_id: int, demands: Sequence[PrepareDemand]
    ) -> PrepareReportView: ...

    async def evaluate_answer(
        self, question_id: int, submission: AnswerSubmission
    ) -> Evaluation | None: ...

    async def generate_fenced(self, source: object | str) -> EntryView: ...
