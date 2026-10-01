"""Model catalog shape and the selection a turn will actually run with.

Only the default model is enabled, so these assert that a model which is not
enabled refuses to be selected rather than silently borrowing another model's
tariff. The token arithmetic itself is pinned where it runs:
`tests/unit/assistant/test_turn_usage_billing.py`.

The tariffs themselves are unverified placeholders — the gateway in use is a
temporary stopgap and production will call the model providers directly. These
tests pin the *conversion*, not the price list, so updating a tariff is a config
edit rather than a test rewrite.
"""

import json
from decimal import Decimal

import pytest

from pycil.billing.units import UNITS_PER_ALLOWANCE_UNIT
from pycil.platform.product_config import SystemConfig, system_config


def test_the_catalog_keeps_every_candidate_on_record():
    model_ids = {m.id for m in system_config.models}
    assert "gemini-3.8-flash" in model_ids
    assert {
        "gemini-2.5-flash",
        "gpt-4o-mini",
        "deepseek-reasoner",
        "claude-3-7-sonnet",
    } <= model_ids


def test_only_the_default_model_is_selectable():
    """Every other candidate is unverified, so none may reach a client."""
    enabled = {m.id for m in system_config.enabled_models()}
    assert enabled == {system_config.assistant.default_model}


def test_the_credit_value_is_the_documented_exchange_rate():
    """1 Credit = USD 0.001 is the anchor every stored milli-credit assumes."""
    assert system_config.app.credit_usd_value == Decimal("0.001")
    assert UNITS_PER_ALLOWANCE_UNIT == 1_000


def test_the_catalog_projection_exposes_only_enabled_models():
    """A client may only choose from the enabled allowlist, with no credentials."""
    from pycil.assistant.schemas import ModelCatalogRead

    catalog = ModelCatalogRead.from_config()
    assert catalog.default_model == system_config.assistant.default_model
    assert [m.id for m in catalog.models] == [m.id for m in system_config.enabled_models()]
    assert all(m.is_default is (m.id == catalog.default_model) for m in catalog.models)
    # The projection is metadata only: nothing that could name a credential or a
    # provider route may reach a client.
    dumped = catalog.model_dump()
    assert "api_key" not in json.dumps(dumped)


def test_a_client_selection_is_validated_against_the_catalog():
    """An unknown model or unsupported effort is refused before any provider call."""
    default_id = system_config.assistant.default_model

    model, effort = system_config.resolve_selection()
    assert (model.id, effort) == (
        default_id,
        system_config.assistant.default_reasoning_effort,
    )

    model, effort = system_config.resolve_selection(default_id, "none")
    assert effort == "none"

    with pytest.raises(ValueError, match="unknown_model"):
        system_config.resolve_selection("not-a-model")
    with pytest.raises(ValueError, match="model_not_enabled"):
        system_config.resolve_selection("claude-3-7-sonnet")
    # An effort outside the vocabulary and one the model does not accept are
    # distinct refusals: the first is a malformed request, the second a valid
    # request for a combination this model cannot run.
    with pytest.raises(ValueError, match="unknown_reasoning_effort"):
        system_config.resolve_selection(default_id, "extreme")


def test_a_non_default_model_does_not_inherit_the_default_effort(monkeypatch):
    """The configured default effort belongs to the default model, not to every model."""
    document = system_config.model_dump()
    document["models"].append(
        {
            "id": "no-reasoning",
            "name": "No Reasoning",
            "provider": "test",
            "enabled": True,
            "pricing": {
                "input_usd_per_m": 1.0,
                "output_usd_per_m": 1.0,
                "cached_read_usd_per_m": 1.0,
            },
            "features": {"vision": False, "reasoning": False},
            "supported_efforts": ["none"],
            "context_window": 1000,
            "max_output_tokens": 100,
        }
    )
    config = SystemConfig.model_validate(document)

    _, effort = config.resolve_selection("no-reasoning")
    assert effort == "none", "a model without reasoning must not be sent the default effort"
    with pytest.raises(ValueError, match="unsupported_reasoning_effort"):
        config.resolve_selection("no-reasoning", "high")
