"""Gated real-OpenRouter contract suite.

These tests make REAL LLM calls (cost money, need network + a real
OPENROUTER_API_KEY) so they are skipped by default. Opt in with:

    RUN_LLM_LIVE=1 uv run pytest -m llm_live

They prove the prompt + schema + parse path actually works against a live
model — the thing unit tests with fake clients cannot prove. Assertions are
semantic-but-tolerant: we pin structure (schema validity, option counts,
verdict mapping) without over-fitting to any one model's exact wording.
"""
from __future__ import annotations

import os

import pytest

_RUN = os.environ.get("RUN_LLM_LIVE", "").lower() in ("1", "true", "yes")
_HAS_KEY = bool(os.environ.get("OPENROUTER_API_KEY", "").strip()) and (
    os.environ.get("OPENROUTER_API_KEY") != "test-fake"
)


def pytest_collection_modifyitems(config, items) -> None:
    """Skip every test in this package unless explicitly opted in.

    A conftest-level `pytestmark` does NOT propagate to sibling test modules,
    so the gate has to be applied per-collected-item here. Skip unless
    RUN_LLM_LIVE=1 AND a real (non-placeholder) OPENROUTER_API_KEY is present.
    """
    if _RUN and _HAS_KEY:
        return
    skip = pytest.mark.skip(
        reason="live LLM suite: set RUN_LLM_LIVE=1 and a real OPENROUTER_API_KEY"
    )
    here = os.path.dirname(__file__)
    for item in items:
        if str(item.fspath).startswith(here):
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _disable_stub(monkeypatch):
    """Force real calls even if WORKER_LLM_STUB leaked into the env."""
    monkeypatch.delenv("WORKER_LLM_STUB", raising=False)
    # Clear the cached settings so a fresh WorkerSettings reads the real env.
    from worker.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
