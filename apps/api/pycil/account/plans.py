from enum import StrEnum


class Plan(StrEnum):
    FREE = "free"
    PRO = "pro"


class Feature(StrEnum):
    ASSISTANT = "assistant"
    ADVANCED_GRADING = "advanced_grading"
