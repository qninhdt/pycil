"""Exercise capabilities and diagnostic categories."""

from enum import StrEnum


class QuestionType(StrEnum):
    DEFINITION_TO_WORD = "definition_to_word"
    CONTEXT_TO_WORD = "context_to_word"
    CLOZE_TO_WORD = "cloze_to_word"
    WORD_TO_DEFINITION = "word_to_definition"
    WORD_TO_USAGE = "word_to_usage"
    DIALOGUE_COMPLETION = "dialogue_completion"
    MEANING_IN_CONTEXT = "meaning_in_context"
    SENTENCE_REWRITE = "sentence_rewrite"


class QuestionArtifactType(StrEnum):
    WORD_DEFINITION = "word_definition"
    WORD_TO_USAGE = "word_to_usage"
    CONTEXT_WORD_MEANING = "context_word_meaning"
    CONTEXT_TO_WORD = "context_to_word"
    DIALOGUE_COMPLETION = "dialogue_completion"
    SENTENCE_REWRITE = "sentence_rewrite"


class ResponseFormat(StrEnum):
    SINGLE_CHOICE = "single_choice"
    SINGLE_WORD = "single_word"
    SHORT_ANSWER = "short_answer"


class TargetPlacement(StrEnum):
    DIALOGUE = "dialogue"
    OPTIONS = "options"


class DefinitionAccuracy(StrEnum):
    ACCURATE = "accurate"
    MIXED = "mixed"
    INACCURATE = "inaccurate"


class DefinitionCoverage(StrEnum):
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    MINIMAL = "minimal"


class UsageMeaning(StrEnum):
    CORRECT = "correct"
    APPROXIMATE = "approximate"
    WRONG = "wrong"


class UsageForm(StrEnum):
    CORRECT = "correct"
    SPELLING_ERROR = "spelling_error"
    FORM_ERROR = "form_error"


class MeaningPreservation(StrEnum):
    PRESERVED = "preserved"
    PARTIAL = "partial"
    CHANGED = "changed"


class Selection(StrEnum):
    AUTO = "auto"
    NEW = "new"
    DUE = "due"


class LearningState(StrEnum):
    ALL = "all"
    NEW = "new"
    DUE = "due"
    NOT_YET_DUE = "not_yet_due"


QUESTION_ARTIFACT_MAP = {
    QuestionType.DEFINITION_TO_WORD: QuestionArtifactType.WORD_DEFINITION,
    QuestionType.WORD_TO_DEFINITION: QuestionArtifactType.WORD_DEFINITION,
    QuestionType.CLOZE_TO_WORD: QuestionArtifactType.CONTEXT_WORD_MEANING,
    QuestionType.MEANING_IN_CONTEXT: QuestionArtifactType.CONTEXT_WORD_MEANING,
    QuestionType.CONTEXT_TO_WORD: QuestionArtifactType.CONTEXT_TO_WORD,
    QuestionType.WORD_TO_USAGE: QuestionArtifactType.WORD_TO_USAGE,
    QuestionType.DIALOGUE_COMPLETION: QuestionArtifactType.DIALOGUE_COMPLETION,
    QuestionType.SENTENCE_REWRITE: QuestionArtifactType.SENTENCE_REWRITE,
}
SINGLETON_ARTIFACT_TYPES = frozenset(
    {QuestionArtifactType.WORD_DEFINITION, QuestionArtifactType.WORD_TO_USAGE}
)
QUESTION_FORMATS = {
    **dict.fromkeys(
        (QuestionType.DEFINITION_TO_WORD, QuestionType.CONTEXT_TO_WORD, QuestionType.CLOZE_TO_WORD),
        frozenset({ResponseFormat.SINGLE_CHOICE, ResponseFormat.SINGLE_WORD}),
    ),
    **dict.fromkeys(
        (
            QuestionType.WORD_TO_DEFINITION,
            QuestionType.WORD_TO_USAGE,
            QuestionType.SENTENCE_REWRITE,
        ),
        frozenset({ResponseFormat.SINGLE_CHOICE, ResponseFormat.SHORT_ANSWER}),
    ),
    **dict.fromkeys(
        (QuestionType.DIALOGUE_COMPLETION, QuestionType.MEANING_IN_CONTEXT),
        frozenset({ResponseFormat.SINGLE_CHOICE}),
    ),
}
ALLOWED_PAIRS = frozenset(
    (kind, fmt) for kind, formats in QUESTION_FORMATS.items() for fmt in formats
)
