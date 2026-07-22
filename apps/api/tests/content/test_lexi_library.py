"""Offline tests for the optional lexi-ai library adapter seam."""

from types import SimpleNamespace

import pytest

from pycil.content import lexi_library
from pycil.content.lexi_library import (
    create_lexicon_reader,
)
from pycil.content.lexi_types import SearchResult

pytestmark = pytest.mark.asyncio


class FakeReaderFacade:
    constructed_with: object | None = None

    def __init__(self, lexicon: object) -> None:
        type(self).constructed_with = lexicon
        self._lexicon = lexicon

    async def get(self, question_id: int):
        if question_id == 99:
            return None
        return SimpleNamespace(
            id=question_id,
            word_id=7,
            sense_id=8,
            format="definition_mcq",
            answer_kind="choice_index",
            payload={"stem": "Choose", "options": ["correct", "wrong"]},
        )

    async def get_question(self, question_id: int):
        return await self.get(question_id)

    async def get_questions_for_sense(self, sense_id: int, fmt: str | None = None):
        assert (sense_id, fmt) == (8, "definition_mcq")
        return [await self.get(13)]

    async def search(self, query):
        assert query == "run"
        return [
            SimpleNamespace(
                display="run",
                entry_type="verb",
                score=0.9,
                lexi_word_id=7,
                cambridge_id=None,
                gloss="move",
            )
        ]

    async def get_entry(self, word_id):
        assert word_id == 7
        return SimpleNamespace(
            word_id=7,
            display="run",
            norm="run",
            status="done",
            entry_type="verb",
            senses=[
                SimpleNamespace(
                    definition="move",
                    tier="core",
                    pos="verb",
                    cefr_level="A1",
                    sense_id=8,
                    examples=["I run."],
                )
            ],
        )

    async def get_senses(self, sense_ids):
        assert sense_ids == [8]
        return (await self.get_entry(7)).senses



def _fake_lexi_ai_module(_name: str) -> SimpleNamespace:
    return SimpleNamespace(
        LexiconReader=FakeReaderFacade,
    )


async def test_library_factory_reports_missing_optional_package(monkeypatch):
    def missing_module(_name: str) -> None:
        raise ModuleNotFoundError("No module named 'lexi_ai'")

    monkeypatch.setattr(lexi_library, "import_module", missing_module)

    with pytest.raises(RuntimeError, match="lexi_ai must be installed"):
        create_lexicon_reader(object())


async def test_library_reader_constructs_and_maps_public_facade(monkeypatch):
    monkeypatch.setattr(lexi_library, "import_module", _fake_lexi_ai_module)
    lexicon = object()
    reader = create_lexicon_reader(lexicon)

    assert not hasattr(reader, "generate")
    assert not hasattr(reader, "generate_questions")
    assert FakeReaderFacade.constructed_with is lexicon
    assert await reader.search("run") == [
        SearchResult("run", "verb", score=0.9, lexi_word_id=7, gloss="move")
    ]
    entry = await reader.get_entry(7)
    assert entry is not None
    assert entry.senses[0].definition == "move"
    assert (await reader.get_senses([8]))[0].sense_id == 8
    question = await reader.get_question(13)
    assert question is not None
    assert question.payload["stem"] == "Choose"
    by_sense = await reader.get_question_for_sense(8, "definition_mcq")
    assert by_sense is not None
    assert by_sense.id == 13
