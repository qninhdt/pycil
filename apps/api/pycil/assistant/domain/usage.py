"""Provider token usage for one assistant turn.

A turn makes an unknown number of model calls: the agent loop may call the model,
run tools, and call it again. Each call reports its own usage, and the turn is
billed for all of them, so usage is accumulated across the turn and converted to
milli-credits exactly once.

The shapes are normalised here rather than at the settlement site because the
providers disagree about where cache reads live. LangChain already flattens the
common OpenAI-compatible field into ``usage_metadata.input_token_details``, and
its key is ``cache_read``; raw provider payloads use ``cached_tokens`` or
``cache_read_input_tokens`` depending on the vendor. All of them mean the same
thing — input tokens served from cache and billed at the cache-read rate — and
counting one twice would over-bill the learner.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pycil.product_config import system_config


@dataclass
class CallUsage:
    """Reported usage from one model call."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def moved_tokens(self) -> bool:
        return (
            self.input_tokens + self.output_tokens + self.cache_write_tokens
        ) > 0


@dataclass(frozen=True)
class ModelRates:
    """The exact tariff captured when a provider call completed."""

    input_usd_per_m: Decimal
    output_usd_per_m: Decimal
    cached_read_usd_per_m: Decimal
    cache_write_usd_per_m: Decimal | None

    @classmethod
    def from_config(cls, pricing) -> "ModelRates":
        return cls(
            input_usd_per_m=pricing.input_usd_per_m,
            output_usd_per_m=pricing.output_usd_per_m,
            cached_read_usd_per_m=pricing.cached_read_usd_per_m,
            cache_write_usd_per_m=pricing.cache_write_usd_per_m,
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "input_usd_per_m": str(self.input_usd_per_m),
            "output_usd_per_m": str(self.output_usd_per_m),
            "cached_read_usd_per_m": str(self.cached_read_usd_per_m),
            "cache_write_usd_per_m": (
                str(self.cache_write_usd_per_m)
                if self.cache_write_usd_per_m is not None
                else None
            ),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ModelRates":
        return cls(
            input_usd_per_m=Decimal(str(value["input_usd_per_m"])),
            output_usd_per_m=Decimal(str(value["output_usd_per_m"])),
            cached_read_usd_per_m=Decimal(str(value["cached_read_usd_per_m"])),
            cache_write_usd_per_m=(
                Decimal(str(value["cache_write_usd_per_m"]))
                if value.get("cache_write_usd_per_m") is not None
                else None
            ),
        )


@dataclass
class PricedUsage:
    model_id: str
    rates: ModelRates
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def moved_tokens(self) -> bool:
        return (
            self.input_tokens + self.output_tokens + self.cache_write_tokens
        ) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "rates": self.rates.to_dict(),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "cache_write_tokens": self.cache_write_tokens,
        }


@dataclass
class TurnUsage:
    """Usage accumulated over every model call in one turn, keyed by model id.

    Keyed rather than summed into one bucket because a turn can legitimately span
    more than one model, and each model is priced at its own tariff. Collapsing
    them first would price one model's tokens at another's rate.
    """

    calls: list[PricedUsage] = field(default_factory=list)
    model_calls: int = 0
    #: Model calls that reported no usable usage. A non-zero count means the turn
    #: was under-metered, which is recorded rather than guessed at.
    unmetered_calls: int = 0

    def add(self, model_id: str, call: CallUsage) -> None:
        self.model_calls += 1
        if not call.moved_tokens:
            self.unmetered_calls += 1
            return
        model = system_config.get_model(model_id)
        if model is None or not model.enabled:
            raise ValueError(f"usage_model_not_enabled: {model_id}")
        rates = ModelRates.from_config(model.pricing)
        bucket = next(
            (
                item
                for item in self.calls
                if item.model_id == model_id and item.rates == rates
            ),
            None,
        )
        if bucket is None:
            bucket = PricedUsage(model_id=model_id, rates=rates)
            self.calls.append(bucket)
        bucket.input_tokens += call.input_tokens
        bucket.output_tokens += call.output_tokens
        bucket.cached_input_tokens += call.cached_input_tokens
        bucket.cache_write_tokens += call.cache_write_tokens

    @property
    def has_usage(self) -> bool:
        return any(bucket.moved_tokens for bucket in self.calls)

    @property
    def has_activity(self) -> bool:
        """Whether any provider call happened, including one without usage fields."""
        return bool(self.calls or self.unmetered_calls)

    @property
    def input_tokens(self) -> int:
        return sum(bucket.input_tokens for bucket in self.calls)

    @property
    def output_tokens(self) -> int:
        return sum(bucket.output_tokens for bucket in self.calls)

    @property
    def cached_input_tokens(self) -> int:
        return sum(bucket.cached_input_tokens for bucket in self.calls)

    @property
    def cache_write_tokens(self) -> int:
        return sum(bucket.cache_write_tokens for bucket in self.calls)

    @property
    def unpriced_cache_write_tokens(self) -> int:
        return sum(
            bucket.cache_write_tokens
            for bucket in self.calls
            if bucket.rates.cache_write_usd_per_m is None
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "calls": [call.to_dict() for call in self.calls],
            "model_calls": self.model_calls,
            "unmetered_calls": self.unmetered_calls,
            "unpriced_cache_write_tokens": self.unpriced_cache_write_tokens,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TurnUsage":
        if not isinstance(value, dict) or value.get("version") != 1:
            raise ValueError("assistant_usage_snapshot_unsupported")
        calls = value.get("calls")
        if not isinstance(calls, list):
            raise ValueError("assistant_usage_snapshot_invalid")
        usage = cls(
            model_calls=_as_int(value.get("model_calls", len(calls))),
            unmetered_calls=_as_int(value.get("unmetered_calls")),
        )
        for call in calls:
            if not isinstance(call, dict) or not isinstance(call.get("model_id"), str):
                raise ValueError("assistant_usage_snapshot_invalid")
            usage.calls.append(
                PricedUsage(
                    model_id=call["model_id"],
                    rates=ModelRates.from_dict(call["rates"]),
                    input_tokens=_as_int(call.get("input_tokens")),
                    output_tokens=_as_int(call.get("output_tokens")),
                    cached_input_tokens=_as_int(call.get("cached_input_tokens")),
                    cache_write_tokens=_as_int(call.get("cache_write_tokens")),
                )
            )
        return usage




def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _cache_read_tokens(details: Any) -> int:
    """Cache-read count from a provider usage detail mapping.

    Keys are matched after normalising case and separators, because the same
    quantity arrives as ``cached_tokens`` (OpenAI), ``cache_read`` (LangChain's
    normalised form) and ``cache_read_input_tokens`` (Anthropic).
    """
    if not isinstance(details, dict):
        return 0
    total = 0
    for key, value in details.items():
        normalised = str(key).lower().replace("-", "_")
        if normalised in {"cached_tokens", "cache_read", "cache_read_input_tokens"}:
            total += _as_int(value)
    return total


def _cache_write_tokens(details: Any) -> int:
    """Cache creation/write tokens from common provider and LangChain fields."""
    if not isinstance(details, dict):
        return 0
    return sum(
        _as_int(value)
        for key, value in details.items()
        if str(key).lower().replace("-", "_")
        in {
            "cache_write",
            "cache_write_tokens",
            "cache_creation",
            "cache_creation_tokens",
            "cache_creation_input_tokens",
            "claude_cache_creation_5_m_tokens",
            "claude_cache_creation_1_h_tokens",
        }
    )


def call_usage(message: Any) -> CallUsage:
    """Read one model response's reported usage.

    Missing usage is not an error: a provider may omit it when a stream is cut
    short, and the caller records that as incomplete metering rather than billing
    a guessed amount. Cached reads are reported inside the input total, so they are
    clamped to it rather than added to it.
    """
    metadata = getattr(message, "usage_metadata", None)
    if not metadata:
        return CallUsage()
    if isinstance(metadata, dict):
        input_tokens = _as_int(metadata.get("input_tokens"))
        output_tokens = _as_int(metadata.get("output_tokens"))
        input_details = metadata.get("input_token_details")
        cached = _cache_read_tokens(input_details) or _cache_read_tokens(metadata)
        cache_write = _cache_write_tokens(input_details) or _cache_write_tokens(metadata)
    else:
        input_tokens = _as_int(getattr(metadata, "input_tokens", 0))
        output_tokens = _as_int(getattr(metadata, "output_tokens", 0))
        input_details = getattr(metadata, "input_token_details", None)
        cached = _cache_read_tokens(input_details) or _cache_read_tokens(metadata)
        cache_write = _cache_write_tokens(input_details) or _cache_write_tokens(metadata)
    cached = min(max(0, cached), max(0, input_tokens))
    cache_write = min(max(0, cache_write), max(0, input_tokens - cached))
    return CallUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached,
        cache_write_tokens=cache_write,
    )


def milli_credits_for(usage: TurnUsage) -> int:
    """Convert accumulated turn usage to a single milli-credit charge.

    Rounded once, after every call in the turn has been summed, so a turn that
    makes several small calls is not rounded up several times. There is no
    artificial minimum charge; the total rounds once at milli-credit precision.
    """
    if not usage.has_usage:
        return 0
    total_usd = Decimal(0)
    for bucket in usage.calls:
        uncached = max(
            0,
            bucket.input_tokens
            - bucket.cached_input_tokens
            - bucket.cache_write_tokens,
        )
        total_usd += (
            Decimal(uncached) * bucket.rates.input_usd_per_m
            + Decimal(bucket.cached_input_tokens) * bucket.rates.cached_read_usd_per_m
            + Decimal(bucket.output_tokens) * bucket.rates.output_usd_per_m
        ) / Decimal(1_000_000)
        if bucket.cache_write_tokens:
            if bucket.rates.cache_write_usd_per_m is not None:
                total_usd += (
                    Decimal(bucket.cache_write_tokens)
                    * bucket.rates.cache_write_usd_per_m
                    / Decimal(1_000_000)
                )
    milli = int(
        (total_usd / system_config.app.credit_usd_value * Decimal(1_000)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    return max(0, milli)
