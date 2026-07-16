"""In-process LexiClient adapter over the lexi-ai Lexicon.

The ONLY module allowed to construct a ``Lexicon`` — every other caller goes
through the ``LexiClient`` port. Questions (generate/grade/get) live on
``lexicon.questions`` (the lazy QuestionEngine), NOT on the Lexicon directly.
The Lexicon binds to lexi-ai's OWN database (LEXI_DB_URL) and must have
``await lexicon.init()`` run once at startup (Phase 11).
"""

from lexi_ai import Entry, Lexicon, Score, SearchResult
from lexi_ai.config import Settings
from lexi_ai.read_models import Question, SenseView

from pycil.config import settings


def build_lexicon() -> Lexicon:
    """Construct a Lexicon bound to lexi-ai's DB + LLM from pycil settings."""
    lexi_settings = Settings(
        db_url=settings.lexi_db_url,
        llm_base_url=settings.lexi_llm_base_url,
        llm_api_key=settings.lexi_llm_api_key,
        llm_model=settings.lexi_llm_model,
        cambridge_db_path=settings.lexi_cambridge_db_path,
    )
    return Lexicon.from_settings(lexi_settings)


class InProcessLexiClient:
    """LexiClient implemented in-process over a single Lexicon instance."""

    def __init__(self, lexicon: Lexicon):
        self._lexicon = lexicon

    async def init(self) -> None:
        """Create lexi-ai's own DB schema (idempotent). Run once at startup."""
        await self._lexicon.init()

    async def search(self, query: str) -> list[SearchResult]:
        return await self._lexicon.search(query)

    async def generate(self, source: SearchResult | str) -> Entry:
        return await self._lexicon.generate(source)

    async def get_entry(self, word_id: int) -> Entry | None:
        try:
            return await self._lexicon.get_entry(word_id)
        except ValueError:
            return None

    async def word_id_for_sense(self, sense_id: int) -> int | None:
        try:
            # This repository lookup is intentionally contained in the adapter:
            # callers only use the stable LexiClient port.
            return await self._lexicon._repo.word_id_for_sense(sense_id)
        except Exception:  # unknown/removed opaque lexi sense
            return None

    async def get_senses(self, sense_ids: list[int]) -> list[SenseView]:
        return await self._lexicon.get_senses(sense_ids)

    async def generate_questions(
        self, entry: Entry, formats: list[str], n: int
    ) -> list[Question]:
        # Question generation lives on the lazy QuestionEngine, not the Lexicon.
        return await self._lexicon.questions.generate(entry, formats=formats, n=n)

    async def grade(self, question: Question, answer: str) -> Score:
        return await self._lexicon.questions.grade(question, answer)

    async def get_question(self, question_id: int) -> Question | None:
        return await self._lexicon.questions.get(question_id)

    async def get_question_for_sense(
        self, sense_id: int, question_format: str
    ) -> Question | None:
        word_id = await self.word_id_for_sense(sense_id)
        if word_id is None:
            return None
        questions = await self._lexicon.questions.list(word_id, question_format)
        return next((q for q in questions if q.sense_id == sense_id), None)
