"""Exact theme namespace selection; unknown themes never fall back to neutral content."""

from sqlalchemy import ColumnElement, ScalarSelect, literal, select

from pycil.themes.errors import InvalidThemeError
from pycil.themes.models import Theme


def normalize_key(value: str) -> str:
    if type(value) is not str or not 1 <= len(value.strip()) <= 255:
        raise InvalidThemeError("invalid theme key")
    return " ".join(value.casefold().split())


def theme_scope(
    theme_id: int | None = None,
    theme_key: str | None = None,
) -> tuple[ScalarSelect[int] | int | None, ColumnElement[bool]]:
    identifier = (
        select(Theme.id).where(Theme.key == normalize_key(theme_key)).scalar_subquery()
        if theme_key is not None
        else theme_id
    )
    valid = (
        literal(True)
        if theme_id is None and theme_key is None
        else select(Theme.id).where(Theme.id == identifier).exists()
    )
    return identifier, valid
