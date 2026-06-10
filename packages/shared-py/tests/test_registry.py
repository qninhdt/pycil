"""Tests for the question plugin registry (Task 1 foundation)."""
from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from shared.questions import registry
from shared.questions.plugin import CheckResult, QuestionPlugin


class _DummyData(BaseModel):
    prompt: str


class _DummyPlugin(QuestionPlugin):
    type_id = "DUMMY_TEST_TYPE"
    data_schema = _DummyData

    @classmethod
    def template_name(cls) -> str:
        return "dummy.md"

    @classmethod
    def prompt_inputs(cls, definition: dict[str, Any], difficulty: str) -> dict[str, Any]:
        return {"term_value": definition.get("term_value")}

    @classmethod
    def sanitize(cls, output: BaseModel) -> dict[str, Any]:
        return output.model_dump()

    @classmethod
    def public_projection(cls, data: dict[str, Any]) -> dict[str, Any]:
        return data

    @classmethod
    def check_answer(cls, data: dict[str, Any], answer: dict[str, Any]) -> CheckResult:
        return CheckResult(correct=True, score=1.0)


@pytest.fixture(autouse=True)
def _clean_dummy() -> Any:
    yield
    registry._REGISTRY.pop("DUMMY_TEST_TYPE", None)


def test_register_and_get() -> None:
    registry.register(_DummyPlugin)
    assert registry.get("DUMMY_TEST_TYPE") is _DummyPlugin
    assert registry.is_registered("DUMMY_TEST_TYPE")


def test_register_is_idempotent_for_same_class() -> None:
    registry.register(_DummyPlugin)
    registry.register(_DummyPlugin)  # no raise
    assert registry.get("DUMMY_TEST_TYPE") is _DummyPlugin


def test_register_conflict_raises() -> None:
    registry.register(_DummyPlugin)

    class _Other(_DummyPlugin):
        pass

    with pytest.raises(ValueError):
        registry.register(_Other)


def test_register_requires_type_id() -> None:
    class _NoId(QuestionPlugin):
        data_schema = _DummyData

        @classmethod
        def template_name(cls) -> str:
            return "x.md"

        @classmethod
        def prompt_inputs(cls, definition: dict[str, Any], difficulty: str) -> dict[str, Any]:
            return {}

        @classmethod
        def sanitize(cls, output: BaseModel) -> dict[str, Any]:
            return {}

        @classmethod
        def public_projection(cls, data: dict[str, Any]) -> dict[str, Any]:
            return data

        @classmethod
        def check_answer(cls, data: dict[str, Any], answer: dict[str, Any]) -> CheckResult:
            return CheckResult(correct=False)

    with pytest.raises(ValueError):
        registry.register(_NoId)


def test_get_unknown_raises() -> None:
    with pytest.raises(registry.UnknownQuestionType):
        registry.get("NOPE_NOT_A_TYPE")


def test_all_types_lists_registered() -> None:
    registry.register(_DummyPlugin)
    assert "DUMMY_TEST_TYPE" in registry.all_types()
    assert registry.all_types() == sorted(registry.all_types())


def test_check_result_explanation_aliases_feedback() -> None:
    r = CheckResult(correct=True, score=1.0, feedback="because")
    assert r.explanation == "because"
