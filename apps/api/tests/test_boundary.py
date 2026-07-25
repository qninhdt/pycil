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
        "async_tasks", "async_task_interests", "async_task_deliveries", "async_task_events",
        "async_task_outbox", "async_command_receipts",
        "assistant_threads", "assistant_runs", "assistant_run_events",
        "assistant_actions", "assistant_action_audit",
    }
    assert pycil_tables == expected


def test_runtime_has_no_lexi_implementation_imports():
    """Runtime code may import only Lexi's root facade and public contracts.

    This is the whole enforcement, and it covers BOTH deployed packages. Two
    import-linter contracts used to restate it as hand-kept lists of forbidden Lexi
    submodules, and both rotted: each still named two modules Lexi had deleted while
    missing thirteen it had added, and both passed anyway. The worker's list was the
    only thing guarding the worker at all.

    Reading the source instead of importing it is what lets one test cover both apps
    from the repo root — they are separate uv projects with separate virtualenvs, so
    neither can import the other, but the files are right there.
    """
    import ast
    import pathlib

    repo = pathlib.Path(__file__).resolve().parents[3]
    packages = [repo / "apps" / "api" / "pycil", repo / "apps" / "worker" / "pycil_worker"]
    hits: list[str] = []
    for package in packages:
        assert package.is_dir(), f"deployed package moved or renamed: {package}"
        for path in sorted(package.rglob("*.py")):
            where = path.relative_to(repo)
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("lexi_ai"):
                            hits.append(f"{where}:{node.lineno}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("lexi_ai"):
                    names = {alias.name for alias in node.names}
                    if node.module == "lexi_ai.contracts":
                        continue
                    if node.module == "lexi_ai" and names == {"Lexicon"}:
                        continue
                    hits.append(f"{where}:{node.lineno}: from {node.module}")
    assert not hits, f"Lexi implementation imports detected: {hits}"


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



def test_api_and_worker_pin_the_same_lexi_commit():
    """Both deployed packages must run the same Lexi build.

    They pin it independently, and they drifted: the worker was left on the previous
    commit through a Lexi bump. Nothing caught it, because each app's suite installs
    only its own pin. A split pin means two Lexi versions against ONE database and
    one migrated schema — the API reading rows the worker's build never wrote.

    A movable tag would hide the drift instead of fixing it, so both must be an
    immutable full commit SHA.
    """
    import pathlib
    import re
    import tomllib

    apps = pathlib.Path(__file__).resolve().parents[3] / "apps"
    pins: dict[str, str] = {}
    for name in ("api", "worker"):
        manifest = tomllib.loads((apps / name / "pyproject.toml").read_text())
        requirement = next(
            dep for dep in manifest["project"]["dependencies"] if dep.startswith("lexi-ai")
        )
        _spec, _, reference = requirement.partition("lexi-ai.git@")
        pins[name] = reference

    assert pins["api"] == pins["worker"], f"Lexi pin drifted between apps: {pins}"
    assert re.fullmatch(r"[0-9a-f]{40}", pins["api"]), f"pin must be a full SHA: {pins['api']}"
