"""theme_service catalog + selection (DB-free).

Pinned:
- Catalog validation: known ids valid, unknown rejected, None allowed.
- rotate_theme_id: concrete session theme stays stable; themed-pool (None)
  rotates deterministically by index.
- Theme is presentation-only — catalog entries never carry grading data.
"""
from __future__ import annotations

from pycil_core.services import theme_service as t


def test_known_and_unknown_theme_validation() -> None:
    assert t.is_valid("space")
    assert t.is_valid(None)  # None → neutral/themed-pool, allowed
    assert not t.is_valid("does-not-exist")


def test_get_theme_returns_catalog_entry() -> None:
    theme = t.get_theme("classic")
    assert theme is not None
    assert theme.id == "classic"
    assert t.get_theme(None) is None
    assert t.get_theme("nope") is None


def test_rotate_keeps_concrete_session_theme_stable() -> None:
    assert t.rotate_theme_id("space", 0) == "space"
    assert t.rotate_theme_id("space", 7) == "space"


def test_rotate_pool_mode_is_deterministic_and_varied() -> None:
    first = t.rotate_theme_id(None, 0)
    second = t.rotate_theme_id(None, 1)
    assert first != second
    # Deterministic: same index → same theme.
    assert t.rotate_theme_id(None, 0) == first


def test_catalog_is_nonempty() -> None:
    ids = {theme.id for theme in t.list_themes()}
    assert "classic" in ids
    assert len(ids) >= 2
