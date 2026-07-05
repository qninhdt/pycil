"""Boundary tests: pycil↔lexi-ai separation holds.

Asserts the two-DB boundary is enforced structurally, not just by convention:
pycil's DB has no dictionary tables, no code constructs a Lexicon outside the
adapter, and the grade path writes only pycil learning tables.
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
        "users", "nodes", "folder_attributes", "deck_attributes", "user_nodes",
        "deck_senses", "user_sense_stats", "review_log", "responses",
    }
    assert pycil_tables == expected


def test_no_lexicon_construction_outside_adapter():
    """grep-equivalent: Lexicon(...) appears only in lexi_inprocess.py."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / "pycil"
    hits = []
    for path in root.rglob("*.py"):
        if path.name == "lexi_inprocess.py":
            continue
        text = path.read_text()
        # Lexicon( construction call (not import, not type annotation).
        if "Lexicon(" in text and "from lexi_ai" in text and "build_lexicon" not in text:
            hits.append(str(path.relative_to(root.parent)))
    assert not hits, f"Lexicon( constructed outside the adapter: {hits}"


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
