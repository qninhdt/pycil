"""Model catalog shape and the token-to-milli-credit conversion.

Only the default model is enabled, so these assert two things: the arithmetic the
ledger will use once settlement is wired, and that a model which is not enabled
refuses to be priced rather than silently borrowing another model's tariff.

The tariffs themselves are unverified placeholders — the gateway in use is a
temporary stopgap and production will call the model providers directly. These
tests pin the *conversion*, not the price list, so updating a tariff is a config
edit rather than a test rewrite.
"""

import json
from decimal import Decimal

import pytest

from pycil.account.plans import MILLI_CREDITS_PER_CREDIT
from pycil.product_config import SystemConfig, system_config


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


def test_a_disabled_model_refuses_to_be_priced():
    """Falling back to another model's tariff would produce an unexplainable invoice."""
    with pytest.raises(ValueError, match="model_not_enabled"):
        system_config.calculate_cost_usd("claude-3-7-sonnet", input_tokens=1_000)
    with pytest.raises(ValueError, match="unknown_model"):
        system_config.calculate_cost_usd("no-such-model", input_tokens=1_000)


def test_cost_is_uncached_input_plus_cache_read_plus_output():
    model = system_config.get_model("gemini-3.8-flash")
    assert model is not None
    pricing = model.pricing

    # 2,000 uncached + 8,000 cached input, 1,000 output.
    cost_usd = system_config.calculate_cost_usd(
        "gemini-3.8-flash",
        input_tokens=10_000,
        output_tokens=1_000,
        cached_tokens=8_000,
    )
    expected = (
        (2_000 * pricing.input_usd_per_m)
        + (8_000 * pricing.cached_read_usd_per_m)
        + (1_000 * pricing.output_usd_per_m)
    ) / 1_000_000
    assert cost_usd == expected


def test_cached_tokens_are_subtracted_from_uncached_input():
    """Providers report cached reads inside the input total, not in addition to it."""
    with_cache = system_config.calculate_cost_usd(
        "gemini-3.8-flash", input_tokens=10_000, cached_tokens=8_000
    )
    without_cache = system_config.calculate_cost_usd("gemini-3.8-flash", input_tokens=10_000)
    assert with_cache < without_cache, "a cached read must not be billed as fresh input"


def test_milli_credits_are_the_usd_cost_over_the_credit_value():
    cost_usd = system_config.calculate_cost_usd(
        "gemini-3.8-flash", input_tokens=1_000_000, output_tokens=0
    )
    milli = system_config.calculate_milli_credits(
        "gemini-3.8-flash", input_tokens=1_000_000, output_tokens=0
    )
    assert milli == round(cost_usd / system_config.app.credit_usd_value * MILLI_CREDITS_PER_CREDIT)


def test_a_tiny_turn_has_no_fabricated_minimum_charge():
    """Round the aggregate token cost once, without inventing a one-milli floor."""
    assert system_config.calculate_milli_credits("gemini-3.8-flash", input_tokens=1) == 0
    assert system_config.calculate_milli_credits("gemini-3.8-flash", input_tokens=2) == 1
    assert system_config.calculate_milli_credits("gemini-3.8-flash") == 0


def test_the_credit_value_is_the_documented_exchange_rate():
    """1 Credit = USD 0.001 is the anchor every stored milli-credit assumes."""
    assert system_config.app.credit_usd_value == Decimal("0.001")
    assert MILLI_CREDITS_PER_CREDIT == 1_000


def test_the_catalog_projection_exposes_only_enabled_models():
    """A client may only choose from the enabled allowlist, with no credentials."""
    from pycil.assistant.domain.schemas import ModelCatalogRead

    catalog = ModelCatalogRead.from_config()
    assert catalog.default_model == system_config.assistant.default_model
    assert [m.id for m in catalog.models] == [
        m.id for m in system_config.enabled_models()
    ]
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
