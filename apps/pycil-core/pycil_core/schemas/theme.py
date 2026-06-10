"""Schemas for learning themes."""
from __future__ import annotations

from pydantic import BaseModel


class ThemeRead(BaseModel):
    """A theme the user can pick for a learning session.

    ``prompt_flavor`` is the optional LLM steering text for the prompt-flavored
    generation path; it is never user-supplied (catalog-only) so it needs no
    sanitization at the boundary.
    """

    id: str
    name: str
    palette: str
    icon: str
    prompt_flavor: str | None = None
