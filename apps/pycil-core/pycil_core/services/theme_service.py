"""Learning theme catalog + selection.

Themes are a presentation/flavor layer — they never affect grading. The catalog
is config-driven (a static dict) so adding a theme is a catalog entry, no schema
change. ``prompt_flavor`` steers the optional prompt-flavored generation path
and is catalog-only (never user-supplied).
"""
from __future__ import annotations

from pycil_core.schemas.theme import ThemeRead

_CATALOG: dict[str, ThemeRead] = {
    "classic": ThemeRead(
        id="classic", name="Classic", palette="neutral", icon="book",
        prompt_flavor=None,
    ),
    "space": ThemeRead(
        id="space", name="Space Explorer", palette="indigo", icon="rocket",
        prompt_flavor="Frame the scenario with a light space-exploration motif.",
    ),
    "ocean": ThemeRead(
        id="ocean", name="Deep Ocean", palette="cyan", icon="waves",
        prompt_flavor="Frame the scenario with a light underwater/ocean motif.",
    ),
    "fantasy": ThemeRead(
        id="fantasy", name="Fantasy Quest", palette="amber", icon="sword",
        prompt_flavor="Frame the scenario with a light fantasy-adventure motif.",
    ),
}

DEFAULT_THEME_ID = "classic"


def list_themes() -> list[ThemeRead]:
    return list(_CATALOG.values())


def get_theme(theme_id: str | None) -> ThemeRead | None:
    if theme_id is None:
        return None
    return _CATALOG.get(theme_id)


def is_valid(theme_id: str | None) -> bool:
    return theme_id is None or theme_id in _CATALOG


def rotate_theme_id(theme_id: str | None, index: int) -> str | None:
    """Per-question theme for the 'different theme per question' feel.

    With a concrete session theme → keep it (stable skin). With no session theme
    (themed-pool mode) → rotate deterministically across the catalog by index so
    each question gets a different theme without randomness.
    """
    if theme_id is not None:
        return theme_id
    ids = sorted(_CATALOG.keys())
    if not ids:
        return None
    return ids[index % len(ids)]
