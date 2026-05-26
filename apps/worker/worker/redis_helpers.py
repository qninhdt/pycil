"""Worker compatibility shim — Redis helpers now live in shared.redis_lock.

Existing worker call sites import `add_spend` / `acquire_or_get_lock` from
this module; this shim re-exports the canonical implementation so we don't
churn every import in one diff.
"""
from __future__ import annotations

from shared.redis_lock import (
    LOCK_LUA as _LOCK_LUA,
    SPEND_KEY_PREFIX,
    acquire_or_get_lock,
    add_spend,
    get_spend_daily,
    spend_key_today as _spend_key_today,
)

__all__ = [
    "_LOCK_LUA",
    "SPEND_KEY_PREFIX",
    "_spend_key_today",
    "acquire_or_get_lock",
    "add_spend",
    "get_spend_daily",
]
