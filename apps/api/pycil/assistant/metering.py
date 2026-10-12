"""Reported completed calls only; aggregate configured units and round once."""

from decimal import ROUND_HALF_UP, Decimal

from langchain_core.callbacks import AsyncCallbackHandler

from pycil.logging import get_logger

logger = get_logger(__name__)


class Meter(AsyncCallbackHandler):
    def __init__(self, rates):
        self.rates = rates
        self.total = Decimal(0)
        self.unmetered_calls = 0

    async def on_llm_end(self, response, **kwargs):
        message = response.generations[0][0].message
        reported = message.usage_metadata
        if not reported or any(
            type(reported.get(key)) is not int or reported[key] < 0
            for key in ("input_tokens", "output_tokens")
        ):
            self.unmetered_calls += 1
            logger.warning("assistant_metering_missing_usage", unmetered_calls=self.unmetered_calls)
            return
        details = reported.get("input_token_details") or {}
        incoming, outgoing = reported["input_tokens"], reported["output_tokens"]
        cached = min(incoming, max(0, details.get("cache_read", 0)))
        written = min(
            incoming - cached, max(0, details.get("cache_creation", details.get("cache_write", 0)))
        )
        self.total += Decimal(incoming - cached - written) * self.rates.input_units_per_token
        self.total += Decimal(cached) * self.rates.cached_read_units_per_token
        self.total += Decimal(outgoing) * self.rates.output_units_per_token
        if written:
            if self.rates.cache_write_units_per_token is None:
                self.unmetered_calls += 1
            else:
                self.total += Decimal(written) * self.rates.cache_write_units_per_token
        logger.info(
            "assistant_llm_usage_recorded",
            input_tokens=incoming,
            output_tokens=outgoing,
            cached_read_tokens=cached,
            cache_write_tokens=written,
            total_units=int(self.units),
        )

    @property
    def units(self):
        return int(self.total.quantize(Decimal(1), rounding=ROUND_HALF_UP))
