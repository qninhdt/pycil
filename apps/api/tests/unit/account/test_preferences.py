from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pycil.account.plans import Plan
from pycil.account.schemas import PreferencesPatch, ProfilePatch
from pycil.account.settings import effective_learning, merge_preferences, preferences
from pycil.account.usage import period_bounds
from pycil.app.config import load_config
from pycil.app.http import Problem
from pycil.study.enums import QuestionType, ResponseFormat


def test_sparse_preferences_merge_preserves_saved_intent_on_free_downgrade():
    config = load_config()
    saved = {
        "learning": {
            "formats": [ResponseFormat.SHORT_ANSWER],
            "question_types": [QuestionType.WORD_TO_DEFINITION],
        },
        "assistant": {"auto_approve": True},
    }
    merged = merge_preferences(
        saved, PreferencesPatch(learning={"questions_per_sense": 2}), Plan.PRO, config
    )
    assert merged["learning"]["formats"] == [ResponseFormat.SHORT_ANSWER]
    assert merged["learning"]["questions_per_sense"] == 2
    assert merged["assistant"]["auto_approve"] is True
    assert "questions_per_sense" not in saved["learning"]
    assert preferences(merged, config).learning.formats == [ResponseFormat.SHORT_ANSWER]
    assert effective_learning(merged, Plan.FREE, config).formats == [ResponseFormat.SINGLE_CHOICE]
    assert effective_learning(merged, Plan.PRO, config).formats == [ResponseFormat.SHORT_ANSWER]


def test_infeasible_preferences_and_unavailable_free_formats_are_distinct_failures():
    config = load_config()
    with pytest.raises(Problem) as error:
        merge_preferences(
            {},
            PreferencesPatch(learning={"formats": [ResponseFormat.SHORT_ANSWER]}),
            Plan.FREE,
            config,
        )
    assert error.value.code == "advanced_grading_not_available"
    with pytest.raises(Problem) as error:
        merge_preferences(
            {},
            PreferencesPatch(
                learning={
                    "formats": [ResponseFormat.SINGLE_WORD],
                    "question_types": [QuestionType.WORD_TO_USAGE],
                }
            ),
            Plan.PRO,
            config,
        )
    assert error.value.code == "invalid_preferences"


def test_profile_patch_distinguishes_omission_null_and_normalizes_fields():
    assert ProfilePatch().model_dump(exclude_unset=True) == {}
    assert ProfilePatch(handle="  Alice_123 ", display_name=" Alice ", bio=None).model_dump(
        exclude_unset=True
    ) == {"handle": "alice_123", "display_name": "Alice", "bio": None}
    for field, value in [
        ("handle", None),
        ("display_name", None),
        ("handle", "éuser"),
        ("handle", "1user"),
        ("handle", "ab"),
        ("handle", "a-bc"),
        ("display_name", " "),
        ("bio", "x" * 501),
    ]:
        with pytest.raises(ValidationError):
            ProfilePatch(**{field: value})


@pytest.mark.parametrize(
    "moment, start, end",
    [
        (
            datetime(2024, 2, 29, 11, 59, tzinfo=UTC),
            datetime(2024, 1, 31, 12, tzinfo=UTC),
            datetime(2024, 2, 29, 12, tzinfo=UTC),
        ),
        (
            datetime(2024, 2, 29, 12, tzinfo=UTC),
            datetime(2024, 2, 29, 12, tzinfo=UTC),
            datetime(2024, 3, 31, 12, tzinfo=UTC),
        ),
        (
            datetime(2025, 2, 28, 12, tzinfo=UTC),
            datetime(2025, 2, 28, 12, tzinfo=UTC),
            datetime(2025, 3, 31, 12, tzinfo=UTC),
        ),
        (
            datetime(2023, 12, 31, 11, 59, tzinfo=UTC),
            datetime(2023, 11, 30, 12, tzinfo=UTC),
            datetime(2023, 12, 31, 12, tzinfo=UTC),
        ),
    ],
)
def test_monthly_period_clamps_each_month_from_original_anchor(moment, start, end):
    assert period_bounds(datetime(2024, 1, 31, 12, tzinfo=UTC), moment) == (start, end)
