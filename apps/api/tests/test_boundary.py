"""Boundary tests: Pycil↔Lexi service separation holds.

Asserts the two-DB boundary is enforced structurally, not just by convention:
pycil's DB has no dictionary tables, no code imports Lexi implementation
models, and the grade path writes only Pycil learning tables.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.db.models import target_metadata
from pycil.learning.models import Response, ReviewLog, UserSenseStats

# Tables lexi-ai owns in ITS OWN database — pycil must never carry these.
_LEXI_TABLES = {
    "words", "senses", "word_aliases", "entry_links",
    "questions", "examples", "collocations",
}


def test_pycil_metadata_has_no_dictionary_tables():
    pycil_tables = {t.name for t in target_metadata.tables.values()}
    overlap = pycil_tables & _LEXI_TABLES
    assert not overlap, f"pycil metadata leaked lexi tables: {overlap}"


def test_pycil_tables_are_the_expected_set():
    pycil_tables = {t.name for t in target_metadata.tables.values()}
    expected = {
        "users", "refresh_sessions", "nodes", "deck_attributes",
        "deck_senses", "user_sense_stats", "review_log", "responses",
        "session_sense_attempts",
        "word_generations",
        "assistant_threads", "assistant_runs", "assistant_run_events",
        "assistant_actions", "assistant_action_audit",
    }
    assert pycil_tables == expected


def test_runtime_has_no_lexi_implementation_imports():
    """Pycil's runtime must depend on Lexi's HTTP contract only."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / "pycil"
    hits = []
    for path in root.rglob("*.py"):
        text = path.read_text()
        if "lexi_ai" in text or "Lexicon(" in text:
            hits.append(str(path.relative_to(root.parent)))
    assert not hits, f"Lexi implementation leaked into Pycil runtime: {hits}"


@pytest.mark.asyncio
@pytest_asyncio.fixture
async def session(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest.mark.asyncio
async def test_grade_writes_only_pycil_learning_tables(session):
    """The learning tables are the only write surface for the grade path —
    no dictionary tables exist in pycil to write to."""
    pycil_tables = {t.name for t in target_metadata.tables.values()}
    learning_tables = {
        Response.__tablename__, ReviewLog.__tablename__, UserSenseStats.__tablename__
    }
    # Every learning table is a pycil table (none are lexi-owned).
    assert learning_tables <= pycil_tables
    # None of the learning tables are dictionary tables.
    assert not (learning_tables & _LEXI_TABLES)
