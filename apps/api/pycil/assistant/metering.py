"""Charge reported usage only; count unmeasured calls and round once."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from pycil.assistant.config import ModelPolicy
from pycil.infrastructure.observability import get_logger

logger = get_logger(__name__)


class Meter(AsyncCallbackHandler):
    rates: ModelPolicy
    total: Decimal
    unknown_calls: int
    pending_calls: set[UUID]

    def __init__(self, rates: ModelPolicy) -> None:
        super().__init__()
        self.rates = rates
        self.total = Decimal(0)
        self.unknown_calls = 0
        self.pending_calls = set()

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self.pending_calls.add(run_id)

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        target_id: UUID | None = run_id or kwargs.get("run_id")
        if target_id is not None:
            self.pending_calls.discard(target_id)
        self.unknown_calls += 1
        logger.warning(
            "assistant_metering_missing_usage",
            error_type=type(error).__name__,
            unmetered_calls=self.unmetered_calls,
        )

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        target_id: UUID | None = run_id or kwargs.get("run_id")
        if target_id is not None:
            self.pending_calls.discard(target_id)
        generations = response.generations
        if not generations or not generations[0]:
            self.unknown_calls += 1
            logger.warning("assistant_metering_missing_usage", unmetered_calls=self.unmetered_calls)
            return
        message = getattr(generations[0][0], "message", None)
        reported = getattr(message, "usage_metadata", None)
        if not isinstance(reported, dict):
            self.unknown_calls += 1
            logger.warning("assistant_metering_missing_usage", unmetered_calls=self.unmetered_calls)
            return

        reported_dict: dict[str, Any] = cast(dict[str, Any], reported)
        details = reported_dict.get("input_token_details")
        if details is not None and not isinstance(details, dict):
            self.unknown_calls += 1
            logger.warning("assistant_metering_missing_usage", unmetered_calls=self.unmetered_calls)
            return

        details_dict: dict[str, Any] = (
            cast(dict[str, Any], details) if isinstance(details, dict) else {}
        )

        incoming = reported_dict.get("input_tokens")
        outgoing = reported_dict.get("output_tokens")
        if (
            type(incoming) is not int
            or incoming < 0
            or type(outgoing) is not int
            or outgoing < 0
            or any(type(val) is not int or val < 0 for val in details_dict.values())
        ):
            self.unknown_calls += 1
            logger.warning("assistant_metering_missing_usage", unmetered_calls=self.unmetered_calls)
            return

        cached = min(incoming, max(0, int(details_dict.get("cache_read", 0) or 0)))
        write_fallback = details_dict.get("cache_creation", details_dict.get("cache_write", 0))
        written = min(incoming - cached, max(0, int(write_fallback or 0)))

        self.total += Decimal(incoming - cached - written) * self.rates.input_units_per_token
        self.total += Decimal(cached) * self.rates.cached_read_units_per_token
        self.total += Decimal(outgoing) * self.rates.output_units_per_token
        if written:
            if self.rates.cache_write_units_per_token is None:
                self.unknown_calls += 1
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
    def unmetered_calls(self) -> int:
        # Cancellation can skip end/error callbacks; started calls still lack a measurement.
        return self.unknown_calls + len(self.pending_calls)

    @property
    def units(self) -> int:
        return int(self.total.quantize(Decimal(1), rounding=ROUND_HALF_UP))
