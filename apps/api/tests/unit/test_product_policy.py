import copy
from datetime import UTC, datetime

import pytest
from lexi_ai import QuestionType, ResponseFormat
from pydantic import ValidationError

from pycil.account.plans import Plan
from pycil.account.schemas import (
    PreferencesPatch,
    effective_learning,
    merge_preferences,
    preferences,
)
from pycil.account.usage import period_bounds
from pycil.config import ProductConfig, load_config
from pycil.http import Problem


def test_config_native_types_and_integer_levels(config):
    assert len(config.learning.pair_levels) == 7
    assert sum(map(len, config.learning.pair_levels.values())) == 12
    assert all(isinstance(kind, QuestionType) for kind in config.learning.pair_levels)
    assert all(
        isinstance(fmt, ResponseFormat) and type(level) is int
        for pairs in config.learning.pair_levels.values()
        for fmt, level in pairs.items()
    )
    assert config.plans[Plan.FREE].monthly_allowance_units == 1_000_000


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(unknown_policy=True),
        lambda d: d["learning"]["defaults"].update(questions_per_sense=8),
        lambda d: d["learning"]["defaults"].update(question_budget=1),
        lambda d: d["learning"]["pair_levels"]["DEFINITION_TO_WORD"].update(SINGLE_CHOICE="1"),
        lambda d: d["learning"]["pair_levels"]["DEFINITION_TO_WORD"].update(SHORT_ANSWER=4),
        lambda d: d["models"].append(copy.deepcopy(d["models"][0])),
        lambda d: d["plans"]["FREE"].update(features=["ASSISTANT", "ADVANCED_GRADING"]),
        lambda d: d["assistant"].update(default_model="not-configured"),
        lambda d: d["cache"].update(actor_ttl_seconds=0),
        lambda d: d["cache"].update(max_entries=-1),
        lambda d: d["cache"].update(max_value_bytes="65536"),
    ],
)
def test_invalid_policy_has_no_fallback(config, mutate):
    data = config.model_dump(mode="json")
    mutate(data)
    with pytest.raises((ValidationError, ValueError)):
        ProductConfig.model_validate(data)


def test_duplicate_yaml_key_is_an_error(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("plans: {}\nplans: {}\n")
    with pytest.raises(ValueError, match="Duplicate"):
        load_config(path)


def test_jsonb_preferences_merge_only_known_levels(config):
    saved = {"locale": "vi", "learning": {"show_explanations": False}}
    patch = PreferencesPatch.model_validate({"learning": {"question_budget": 12}})
    merged = merge_preferences(saved, patch, Plan.FREE, config)
    assert merged == {
        "locale": "vi",
        "learning": {"show_explanations": False, "question_budget": 12},
    }
    assert saved["learning"] == {"show_explanations": False}
    assert preferences({}, config).timezone == "UTC"
    assert effective_learning(merged, Plan.FREE, config).question_budget == 12


@pytest.mark.parametrize(
    "body",
    [
        {"plan": "PRO"},
        {"timezone": None},
        {"learning": None},
        {"learning": {"show_explanations": None}},
        {"learning": {"session_id": "x"}},
    ],
)
def test_unknown_or_null_settings_rejected(body):
    with pytest.raises(ValidationError):
        PreferencesPatch.model_validate(body)


def test_paid_preferences_preserved_on_downgrade(config):
    patch = PreferencesPatch.model_validate(
        {
            "learning": {
                "formats": ["SINGLE_WORD"],
                "questions_per_sense": 3,
            }
        }
    )
    saved = merge_preferences({}, patch, Plan.PRO, config)
    with pytest.raises(Problem, match="advanced_grading_not_available"):
        merge_preferences({}, patch, Plan.FREE, config)
    with pytest.raises(Problem, match="infeasible_learning_preferences"):
        effective_learning(saved, Plan.FREE, config)
    assert preferences(saved, config).learning.formats == [ResponseFormat.SINGLE_WORD]
    assert (
        merge_preferences(saved, PreferencesPatch(locale="vi"), Plan.FREE, config)["learning"]
        == saved["learning"]
    )


def test_month_end_anchor_does_not_drift():
    anchor = datetime(2026, 1, 31, 12, tzinfo=UTC)
    start, end = period_bounds(anchor, datetime(2026, 3, 1, tzinfo=UTC))
    assert start == datetime(2026, 2, 28, 12, tzinfo=UTC)
    assert end == datetime(2026, 3, 31, 12, tzinfo=UTC)
    assert period_bounds(anchor, end)[0] == end
