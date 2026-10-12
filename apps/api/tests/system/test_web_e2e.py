"""Opt-in frontend E2E entry using real identity and isolated native stores."""

import os

import pytest

from tests.support.web_e2e_environment import run_web_e2e

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_WEB_E2E") != "1", reason="Run pnpm test:e2e from apps/web"
)


async def test_full_stack(
    database, dictionary, deployment, config, monkeypatch, tmp_path, reference
):
    await run_web_e2e(database, dictionary, deployment, config, monkeypatch, tmp_path, reference)
