"""Assistant turn billing: reported usage in, one settlement out.

The turn is the billing unit. A turn may call the model several times around tool
calls, and the ledger must receive exactly one entry whose amount reflects every
call's reported tokens. These tests drive the accumulator and the pricing
conversion directly, because the arithmetic is the part that can silently
mis-bill a learner.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from pycil.assistant.domain import usage as usage_module
from pycil.assistant.domain.usage import (
    CallUsage,
    TurnUsage,
    call_usage,
    milli_credits_for,
)
from pycil.product_config import SystemConfig, system_config


def _message(**usage) -> SimpleNamespace:
    return SimpleNamespace(usage_metadata=usage)


def test_usage_is_read_from_langchains_normalised_metadata():
    """LangChain flattens provider shapes into `usage_metadata`; cache lives in the details."""
    call = call_usage(
        _message(input_tokens=1000, output_tokens=500, input_token_details={"cache_read": 800})
    )
    assert (call.input_tokens, call.output_tokens, call.cached_input_tokens) == (1000, 500, 800)


@pytest.mark.parametrize(
    "details",
    [
        {"cache_read": 700},
        {"cached_tokens": 700},
        {"cache_read_input_tokens": 700},
    ],
)
def test_every_provider_cache_key_means_the_same_quantity(details):
    """OpenAI, Anthropic and LangChain each name the cache read differently."""
    assert call_usage(_message(input_tokens=900, output_tokens=1, input_token_details=details)
                      ).cached_input_tokens == 700


def test_cached_reads_are_clamped_to_the_input_total():
    """A cached count larger than the input total must not produce a negative uncached count."""
    call = call_usage(
        _message(input_tokens=100, output_tokens=10, input_token_details={"cache_read": 500})
    )
    assert call.cached_input_tokens == 100


def test_cache_writes_are_normalized_and_billed_at_their_own_rate(monkeypatch):
    document = system_config.model_dump()
    model = next(m for m in document["models"] if m["id"] == "gemini-3.8-flash")
    model["pricing"]["cache_write_usd_per_m"] = 0.2
    monkeypatch.setattr(usage_module, "system_config", SystemConfig.model_validate(document))

    call = call_usage(
        _message(
            input_tokens=1_000,
            output_tokens=0,
            input_token_details={"cache_read": 600, "cache_write": 300},
        )
    )
    usage = TurnUsage()
    usage.add("gemini-3.8-flash", call)

    assert (call.cached_input_tokens, call.cache_write_tokens) == (600, 300)
    assert milli_credits_for(usage) == 135


def test_a_call_without_usage_is_counted_not_silently_free():
    """A provider that omits usage must surface as incomplete metering, not a zero bill."""
    usage = TurnUsage()
    usage.add("m", call_usage(SimpleNamespace(usage_metadata=None)))
    assert usage.unmetered_calls == 1
    assert not usage.has_usage
    assert milli_credits_for(usage) == 0


def test_several_calls_in_one_turn_accumulate_before_rounding():
    """Rounding per call would over-charge a turn that makes many small calls."""
    usage = TurnUsage()
    for _ in range(3):
        usage.add("gemini-3.8-flash", CallUsage(input_tokens=400, output_tokens=100))

    assert usage.input_tokens == 1200
    assert usage.output_tokens == 300

    per_model = system_config.calculate_cost_usd(
        "gemini-3.8-flash", input_tokens=1200, output_tokens=300
    )
    assert milli_credits_for(usage) == round(
        per_model / system_config.app.credit_usd_value * 1_000
    )


def test_each_model_in_a_turn_is_priced_at_its_own_tariff(monkeypatch):
    """A turn that switched models must not bill one model's tokens at another's rate.

    The catalog ships with one enabled model, so a second is added here at a
    deliberately different tariff to prove the per-model keying is real. The
    catalog is frozen, so this replaces the loaded configuration rather than
    mutating it.
    """
    default_id = system_config.assistant.default_model
    expensive_id = "expensive-model"
    document = system_config.model_dump()
    document["models"].append(
        {
            "id": expensive_id,
            "name": "Expensive",
            "provider": "test",
            "enabled": True,
            "pricing": {
                "input_usd_per_m": 9_999.0,
                "output_usd_per_m": 9_999.0,
                "cached_read_usd_per_m": 9_999.0,
            },
            "features": {"vision": False, "reasoning": False},
            "supported_efforts": ["none"],
            "context_window": 1000,
            "max_output_tokens": 100,
        }
    )
    monkeypatch.setattr(usage_module, "system_config", SystemConfig.model_validate(document))

    mixed = TurnUsage()
    mixed.add(default_id, CallUsage(input_tokens=1_000_000))
    mixed.add(expensive_id, CallUsage(input_tokens=1_000_000))

    only_default = TurnUsage()
    only_default.add(default_id, CallUsage(input_tokens=2_000_000))

    assert milli_credits_for(mixed) > milli_credits_for(only_default)


def test_resume_keeps_the_tariffs_snapshotted_for_earlier_calls(monkeypatch):
    usage = TurnUsage()
    usage.add("gemini-3.8-flash", CallUsage(input_tokens=1_000_000))
    snapshot = usage.to_dict()

    document = system_config.model_dump()
    model = next(m for m in document["models"] if m["id"] == "gemini-3.8-flash")
    model["pricing"]["input_usd_per_m"] *= 2
    monkeypatch.setattr(usage_module, "system_config", SystemConfig.model_validate(document))

    resumed = TurnUsage.from_dict(snapshot)
    resumed.add("gemini-3.8-flash", CallUsage(input_tokens=1_000_000))

    assert len(resumed.calls) == 2
    assert resumed.calls[0].rates.input_usd_per_m == Decimal("0.30")
    assert resumed.calls[1].rates.input_usd_per_m == Decimal("0.60")
    assert milli_credits_for(resumed) == 900_000


def test_a_tiny_turn_has_no_fabricated_minimum_charge():
    usage = TurnUsage()
    usage.add("gemini-3.8-flash", CallUsage(input_tokens=1))
    assert milli_credits_for(usage) == 0
    usage.add("gemini-3.8-flash", CallUsage(input_tokens=1))
    assert milli_credits_for(usage) == 1


def test_the_milli_credit_conversion_matches_the_credit_value():
    """1 Credit = USD 0.001 is the anchor the stored integer assumes."""
    usage = TurnUsage()
    usage.add("gemini-3.8-flash", CallUsage(input_tokens=1_000_000, output_tokens=0))
    cost_usd = system_config.calculate_cost_usd(
        "gemini-3.8-flash", input_tokens=1_000_000, output_tokens=0
    )
    assert milli_credits_for(usage) == round(cost_usd / system_config.app.credit_usd_value * 1_000)


@pytest.mark.asyncio
async def test_the_metering_middleware_reads_usage_off_the_response_messages():
    """LangChain hands the middleware a `ModelResponse`, not a bare message.

    Usage lives on the messages inside `ModelResponse.result`, so reading it off
    the wrapper finds nothing and the turn bills zero. This pins the shape the
    middleware must actually read.
    """
    from uuid import uuid4

    from langchain.agents.middleware import ModelResponse
    from langchain_core.messages import AIMessage

    from pycil.assistant.application.middleware import UsageMeteringMiddleware
    from pycil.assistant.domain.context import AssistantContext

    context = AssistantContext(user_id=uuid4())
    response = ModelResponse(
        result=[
            AIMessage(
                content="hi",
                usage_metadata={
                    "input_tokens": 900,
                    "output_tokens": 40,
                    "total_tokens": 940,
                    "input_token_details": {"cache_read": 600},
                },
            )
        ]
    )

    middleware = UsageMeteringMiddleware()
    request = SimpleNamespace(
        model=SimpleNamespace(model_name="gemini-3.8-flash"),
        runtime=SimpleNamespace(context=context),
    )

    async def handler(_request):
        return response

    await middleware.awrap_model_call(request, handler)

    assert context.usage.input_tokens == 900
    assert context.usage.output_tokens == 40
    assert context.usage.cached_input_tokens == 600
    assert context.usage.unmetered_calls == 0
