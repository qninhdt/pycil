"""Worker test scaffold. Most jobs need integration env (Postgres, Redis,
OpenRouter mock) so tests are gated on env vars and act as smoke checks
when those are unavailable.
"""
from __future__ import annotations

import os

import pytest


REQUIRES_DB = pytest.mark.skipif(
    not os.getenv("DATABASE_URL_TEST"),
    reason="DATABASE_URL_TEST not set",
)
REQUIRES_REDIS = pytest.mark.skipif(
    not os.getenv("REDIS_URL"),
    reason="REDIS_URL not set",
)
