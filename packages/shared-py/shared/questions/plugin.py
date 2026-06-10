"""Question plugin contract + generic result type.

Every question type is a plugin: a class implementing :class:`QuestionPlugin`.
Plugins self-register into :mod:`shared.questions.registry` on import. Adding a
new question type means dropping in a new plugin module and registering it — no
edits to the worker pipeline, the API dispatch, the grading dispatch, or the
FE registry's backend counterpart.

The contract is expressed with classmethods so a plugin *is* the class itself
(no instance state); the registry stores class objects.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


@dataclass
class CheckResult:
    """Generic grading result returned by every plugin.

    - ``correct``: pass/fail verdict the learning loop consumes.
    - ``score``: 0.0..1.0 credit/confidence. MCQ uses 1.0/0.0; graded free-text
      may report partial confidence from the tiered ladder / LLM judge.
    - ``feedback``: human-readable explanation surfaced post-submit.
    - ``reveal``: type-specific payload disclosed only *after* submit — e.g. an
      MCQ's ``correct_index`` or a Write question's ``expected_answer``.
    """

    correct: bool
    score: float = 0.0
    feedback: str | None = None
    reveal: dict[str, Any] = field(default_factory=dict)

    # Backward-compat shim: legacy call sites read ``.explanation``.
    @property
    def explanation(self) -> str | None:
        return self.feedback


class QuestionPlugin(ABC):
    """Contract every question type implements."""

    #: Stable string identifier persisted in ``questions.type`` (varchar).
    type_id: str

    #: Pydantic model describing the persisted ``questions.data`` JSONB shape
    #: and the LLM structured-output target the worker validates against.
    data_schema: type[BaseModel]

    #: True when a correct verdict needs server-side resources (LLM judge,
    #: fuzzy ladder) beyond the pure ``check_answer`` fast path. The grading
    #: branch dispatches an async grade job for these; sync plugins are graded
    #: inline by ``check_answer``. No separate grading-strategy registry.
    requires_server_grading: bool = False

    @classmethod
    @abstractmethod
    def template_name(cls) -> str:
        """Jinja2 template filename under ``apps/worker/prompts/``."""

    @classmethod
    @abstractmethod
    def prompt_inputs(
        cls, definition: dict[str, Any], difficulty: str, theme: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Variables passed to the Jinja2 template render.

        ``theme`` is an optional presentation-flavor passthrough (catalog-only
        steering text) for the prompt-flavored generation path. Plugins may
        ignore it; the live session path runs render-only (theme=None)."""

    @classmethod
    @abstractmethod
    def sanitize(cls, output: BaseModel) -> dict[str, Any]:
        """Convert validated LLM output into the persisted JSONB dict, stripping
        URLs/HTML/control chars from free-text fields."""

    @classmethod
    @abstractmethod
    def public_projection(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Drop fields that would reveal the answer pre-submit."""

    @classmethod
    @abstractmethod
    def check_answer(
        cls, data: dict[str, Any], answer: dict[str, Any]
    ) -> CheckResult:
        """Validate the generic ``{answer: ...}`` payload against persisted
        ``data``. ``answer`` is the inner object the API received under the
        ``answer`` key — each plugin parses its own shape."""
