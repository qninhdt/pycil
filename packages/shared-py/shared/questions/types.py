"""Question type identifiers.

Neutral home for the ``QuestionType`` enum so both the DB layer
(``shared.db.enums``) and the question plugins can import it without depending
on the legacy ``base`` module (removed during the plugin migration).
"""
from __future__ import annotations

from enum import Enum


class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    WRITE = "WRITE"
    FILL_IN_BLANK = "FILL_IN_BLANK"
