"""Public API for the shared question package.

Importing this package self-registers all builtin question plugins into
:mod:`shared.questions.registry`.
"""
from shared.questions.plugin import CheckResult, QuestionPlugin
from shared.questions.plugins.fill_in_blank import (
    FillAnswerInput,
    FillData,
    FillInBlankQuestion,
)
from shared.questions.plugins.multiple_choice import (
    MCQAnswerInput,
    MCQData,
    MultipleChoiceQuestion,
)
from shared.questions.plugins.write import (
    WriteAnswerInput,
    WriteData,
    WriteQuestion,
)
from shared.questions.types import QuestionType

# Side-effect import: registers all builtin plugins.
from shared.questions import plugins as _plugins  # noqa: E402,F401
from shared.questions import registry  # noqa: E402

__all__ = [
    "QuestionType",
    "QuestionPlugin",
    "CheckResult",
    "registry",
    "MCQData",
    "MCQAnswerInput",
    "MultipleChoiceQuestion",
    "WriteData",
    "WriteAnswerInput",
    "WriteQuestion",
    "FillData",
    "FillAnswerInput",
    "FillInBlankQuestion",
]
