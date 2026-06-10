"""Database enums shared across runtime apps."""
from __future__ import annotations

from enum import Enum

from shared.questions.types import QuestionType


class NodeType(str, Enum):
    FOLDER = "FOLDER"
    DECK = "DECK"
    SHORTCUT = "SHORTCUT"


class Visibility(str, Enum):
    PRIVATE = "PRIVATE"
    PUBLIC = "PUBLIC"


class TermType(str, Enum):
    SINGLE_WORD = "SINGLE_WORD"
    COMPOUND_WORD = "COMPOUND_WORD"
    FIXED_PHRASE = "FIXED_PHRASE"
    PATTERN_PHRASE = "PATTERN_PHRASE"


class CefrLevel(str, Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class PartOfSpeech(str, Enum):
    NOUN = "NOUN"
    VERB = "VERB"
    ADJECTIVE = "ADJECTIVE"
    ADVERB = "ADVERB"
    PRONOUN = "PRONOUN"
    PREPOSITION = "PREPOSITION"
    CONJUNCTION = "CONJUNCTION"
    INTERJECTION = "INTERJECTION"
    DETERMINER = "DETERMINER"
    NUMERAL = "NUMERAL"
    PARTICLE = "PARTICLE"
    OTHER = "OTHER"


class UserTermStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BURIED = "buried"


class ProfileVisibility(str, Enum):
    PRIVATE = "private"
    FRIENDS = "friends"
    PUBLIC = "public"


class ClassroomRole(str, Enum):
    TEACHER = "teacher"
    STUDENT = "student"


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


__all__ = [
    "CefrLevel",
    "ClassroomRole",
    "NodeType",
    "PartOfSpeech",
    "ProfileVisibility",
    "QuestionType",
    "TermType",
    "UserRole",
    "UserTermStatus",
    "Visibility",
]
