from enum import StrEnum


class Plan(StrEnum):
    FREE = "FREE"
    PRO = "PRO"


class Feature(StrEnum):
    ASSISTANT = "ASSISTANT"
    ADVANCED_GRADING = "ADVANCED_GRADING"
