"""Question type registry.

A process-global map of ``type_id -> QuestionPlugin`` class. Builtin plugins
self-register on import (see :mod:`shared.questions.plugins`). Third-party or
drop-in plugins call :func:`register` from their own module.

Consumers (worker pipeline, API dispatch, grading dispatch) resolve a plugin by
its persisted ``questions.type`` string and never branch on concrete types.
"""
from __future__ import annotations

from shared.questions.plugin import QuestionPlugin

_REGISTRY: dict[str, type[QuestionPlugin]] = {}


class UnknownQuestionType(KeyError):
    """Raised when a ``type_id`` has no registered plugin."""

    def __init__(self, type_id: str) -> None:
        self.type_id = type_id
        super().__init__(f"unknown_question_type: {type_id!r}")


def register(plugin: type[QuestionPlugin]) -> type[QuestionPlugin]:
    """Register a plugin class. Idempotent for the same class; raises on a
    conflicting re-registration of a different class under the same id.

    Returns the class so it can be used as a decorator.
    """
    type_id = getattr(plugin, "type_id", None)
    if not type_id or not isinstance(type_id, str):
        raise ValueError(f"plugin {plugin!r} must define a non-empty str type_id")
    existing = _REGISTRY.get(type_id)
    if existing is not None and existing is not plugin:
        raise ValueError(
            f"question type {type_id!r} already registered to {existing!r}"
        )
    _REGISTRY[type_id] = plugin
    return plugin


def get(type_id: str) -> type[QuestionPlugin]:
    """Resolve a plugin by its ``type_id``. Raises :class:`UnknownQuestionType`."""
    try:
        return _REGISTRY[type_id]
    except KeyError as exc:
        raise UnknownQuestionType(type_id) from exc


def is_registered(type_id: str) -> bool:
    return type_id in _REGISTRY


def all_types() -> list[str]:
    """Sorted list of registered ``type_id`` values."""
    return sorted(_REGISTRY)


def all_plugins() -> dict[str, type[QuestionPlugin]]:
    """Shallow copy of the registry map."""
    return dict(_REGISTRY)
