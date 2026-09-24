"""Startup validation of the committed product policy.

The configuration file is the single owner of every tunable value, which means a
typo in it changes what a learner is charged or how long a session runs. These
cases pin the refusals: each invalid document must fail with the offending field
named, rather than starting the process on a silent default.

Every case writes a real temporary YAML file and loads it through the production
loader, so the path resolution and the section-order check are exercised too.
"""

from __future__ import annotations

import copy
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from pycil.product_config import (
    SECTION_ORDER,
    SystemConfig,
    load_system_config,
    resolve_config_path,
)

# A minimal valid document. Each case below mutates exactly one thing so a
# failure names its own cause rather than a cascade.
_VALID: dict = {
    "app": {
        "credit_usd_value": 0.001,
        "plans": {"free": {"monthly_credits": 1000}, "pro": {"monthly_credits": 10000}},
    },
    "learning": {
        "max_words_per_session": 30,
        "max_questions_per_round": 15,
        "session_ttl_seconds": 86400,
        "rubric_grading_credits": 1.0,
    },
    "content": {"singleflight_timeout_seconds": 30},
    "assistant": {
        "turn_timeout_seconds": 60,
        "max_tool_calls_per_turn": 10,
        "default_model": "test-model",
        "default_reasoning_effort": "none",
    },
    "models": [
        {
            "id": "test-model",
            "name": "Test Model",
            "provider": "test",
            "pricing": {
                "input_usd_per_m": 1.0,
                "output_usd_per_m": 2.0,
                "cached_read_usd_per_m": 0.5,
            },
            "features": {"vision": True, "reasoning": True},
            "supported_efforts": ["none", "low"],
            "context_window": 1000,
            "max_output_tokens": 100,
        }
    ],
}


def _write(tmp_path: Path, document) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _valid(tmp_path: Path) -> Path:
    return _write(tmp_path, copy.deepcopy(_VALID))


def test_the_shipped_configuration_loads_and_lists_sections_in_order():
    """The committed file is itself the first test case."""
    resolved = resolve_config_path()
    assert resolved.is_file(), f"committed configuration missing at {resolved}"
    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    assert tuple(raw) == SECTION_ORDER

    config = load_system_config(resolved)
    assert config.app.plans["free"].monthly_credits == 1000
    assert config.app.plans["pro"].monthly_credits == 10000
    assert config.get_model(config.assistant.default_model) is not None


def test_valid_document_parses(tmp_path):
    config = load_system_config(_valid(tmp_path))
    assert isinstance(config, SystemConfig)
    assert config.assistant.default_model == "test-model"


def test_missing_file_fails_rather_than_falling_back(tmp_path):
    with pytest.raises(RuntimeError, match="not found"):
        load_system_config(tmp_path / "absent.yaml")


def test_wrong_section_order_fails(tmp_path):
    document = copy.deepcopy(_VALID)
    # Rebuilding the mapping is what actually reorders it; assigning to an
    # existing key keeps its original position, which would make this pass
    # vacuously.
    document = {
        "app": document["app"],
        "learning": document["learning"],
        "models": document["models"],
        "content": document["content"],
        "assistant": document["assistant"],
    }
    with pytest.raises(RuntimeError, match="sections must be"):
        load_system_config(_write(tmp_path, document))


def test_unknown_key_is_rejected(tmp_path):
    document = copy.deepcopy(_VALID)
    document["learning"]["target_retention"] = 0.9
    with pytest.raises(Exception, match="target_retention"):
        load_system_config(_write(tmp_path, document))


def test_missing_section_is_rejected(tmp_path):
    document = copy.deepcopy(_VALID)
    del document["assistant"]
    with pytest.raises(Exception, match="assistant"):
        load_system_config(_write(tmp_path, document))


def test_duplicate_model_id_is_rejected(tmp_path):
    document = copy.deepcopy(_VALID)
    document["models"].append(copy.deepcopy(document["models"][0]))
    with pytest.raises(Exception, match="duplicate model id"):
        load_system_config(_write(tmp_path, document))


def test_default_model_absent_from_catalog_is_rejected(tmp_path):
    document = copy.deepcopy(_VALID)
    document["assistant"]["default_model"] = "not-in-catalog"
    with pytest.raises(Exception, match="not in models"):
        load_system_config(_write(tmp_path, document))


def test_disabled_default_model_is_rejected(tmp_path):
    document = copy.deepcopy(_VALID)
    document["models"][0]["enabled"] = False
    with pytest.raises(Exception, match="is disabled"):
        load_system_config(_write(tmp_path, document))


def test_default_effort_unsupported_by_its_model_is_rejected(tmp_path):
    document = copy.deepcopy(_VALID)
    document["assistant"]["default_reasoning_effort"] = "high"
    with pytest.raises(Exception, match="is not supported by"):
        load_system_config(_write(tmp_path, document))


def test_unknown_reasoning_effort_is_rejected(tmp_path):
    document = copy.deepcopy(_VALID)
    document["models"][0]["supported_efforts"] = ["none", "extreme"]
    with pytest.raises(Exception, match="unknown"):
        load_system_config(_write(tmp_path, document))


@pytest.mark.parametrize(
    "field,value",
    [
        ("input_usd_per_m", -0.01),
        ("output_usd_per_m", -1.0),
        ("cached_read_usd_per_m", -0.5),
    ],
)
def test_negative_tariff_is_rejected(tmp_path, field, value):
    document = copy.deepcopy(_VALID)
    document["models"][0]["pricing"][field] = value
    with pytest.raises(Exception, match=field):
        load_system_config(_write(tmp_path, document))


@pytest.mark.parametrize(
    "field",
    ["max_words_per_session", "max_questions_per_round", "session_ttl_seconds"],
)
def test_non_positive_duration_or_bound_is_rejected(tmp_path, field):
    document = copy.deepcopy(_VALID)
    document["learning"][field] = 0
    with pytest.raises(Exception, match=field):
        load_system_config(_write(tmp_path, document))


def test_zero_monthly_allowance_is_rejected(tmp_path):
    document = copy.deepcopy(_VALID)
    document["app"]["plans"]["free"]["monthly_credits"] = 0
    with pytest.raises(Exception, match="monthly_credits"):
        load_system_config(_write(tmp_path, document))


def test_public_catalog_projection_carries_no_credentials():
    """The enabled-model view is what a client may see, so it must be policy only.

    Pins the exact field set rather than pattern-matching names, because a
    substring rule both misses a field called ``auth`` and false-positives on a
    legitimate one like ``max_output_tokens``. A new field reaching the
    projection has to be added here deliberately.
    """
    config = load_system_config(resolve_config_path())
    allowed = {
        "id",
        "name",
        "provider",
        "enabled",
        "pricing",
        "features",
        "supported_efforts",
        "context_window",
        "max_output_tokens",
    }
    assert config.enabled_models(), "catalog has no enabled model to project"
    for model in config.enabled_models():
        assert set(model.model_dump()) == allowed


def test_a_rubric_cost_below_one_milli_credit_is_rejected(tmp_path):
    """The ledger's resolution is one milli-credit, so a smaller cost is invalid.

    At 0.0004 Credits the cost rounds to zero, and the two live consumers then
    fail at runtime rather than at startup: `human_estimate` divides by it, and
    the grading debit rejects a non-positive amount.
    """
    document = copy.deepcopy(_VALID)
    document["learning"]["rubric_grading_credits"] = 0.0004
    with pytest.raises(Exception, match="rubric_grading_credits"):
        load_system_config(_write(tmp_path, document))


def test_one_milli_credit_is_accepted_as_the_floor(tmp_path):
    document = copy.deepcopy(_VALID)
    document["learning"]["rubric_grading_credits"] = 0.001
    config = load_system_config(_write(tmp_path, document))
    assert config.learning.rubric_grading_credits == Decimal("0.001")


def test_an_unknown_model_cannot_be_billed(tmp_path):
    """Billing must refuse an unknown id rather than charging the default tariff."""
    config = load_system_config(_valid(tmp_path))
    with pytest.raises(ValueError, match="unknown_model"):
        config.calculate_cost_usd("no-such-model", input_tokens=10, output_tokens=10)


def test_a_disabled_model_cannot_be_billed(tmp_path):
    document = copy.deepcopy(_VALID)
    document["models"].append(
        {
            **copy.deepcopy(document["models"][0]),
            "id": "retired-model",
            "enabled": False,
        }
    )
    config = load_system_config(_write(tmp_path, document))
    with pytest.raises(ValueError, match="model_not_enabled"):
        config.calculate_cost_usd("retired-model", input_tokens=10)


@pytest.mark.parametrize(
    "features, efforts",
    [
        # Advertises reasoning levels but claims no reasoning capability.
        ({"vision": True, "reasoning": False}, ["none", "high"]),
        # Claims reasoning capability but offers nowhere to put it.
        ({"vision": True, "reasoning": True}, ["none"]),
    ],
)
def test_reasoning_capability_must_match_the_advertised_efforts(tmp_path, features, efforts):
    """The two fields cannot disagree, or a turn silently loses its reasoning."""
    document = copy.deepcopy(_VALID)
    document["models"][0]["features"] = features
    document["models"][0]["supported_efforts"] = efforts
    with pytest.raises(Exception, match="reasoning"):
        load_system_config(_write(tmp_path, document))


def test_loaded_configuration_is_immutable(tmp_path):
    """Policy is fixed for the process lifetime, not merely by convention."""
    config = load_system_config(_valid(tmp_path))
    with pytest.raises(ValidationError):
        config.assistant.turn_timeout_seconds = 999
