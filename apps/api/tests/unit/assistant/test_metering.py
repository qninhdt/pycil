from decimal import Decimal
from types import SimpleNamespace

import pytest

from pycil.assistant.metering import Meter


def response(usage):
    return SimpleNamespace(
        generations=[[SimpleNamespace(message=SimpleNamespace(usage_metadata=usage))]]
    )


def rates(**changes):
    return SimpleNamespace(
        **(
            dict(
                input_units_per_token=Decimal(".1"),
                output_units_per_token=Decimal(".2"),
                cached_read_units_per_token=Decimal(".01"),
                cache_write_units_per_token=Decimal(".3"),
            )
            | changes
        )
    )


async def test_meter_separates_cached_written_tokens_and_rounds_once():
    meter = Meter(rates())
    await meter.on_llm_end(
        response(
            {
                "input_tokens": 10,
                "output_tokens": 2,
                "input_token_details": {"cache_read": 3, "cache_creation": 2},
            }
        )
    )
    assert meter.total == Decimal("1.53")
    assert meter.units == 2
    small = Meter(rates())
    for _ in range(6):
        await small.on_llm_end(response({"input_tokens": 1, "output_tokens": 0}))
    assert small.total == Decimal(".6") and small.units == 1


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {"input_tokens": True, "output_tokens": 0},
        {"input_tokens": -1, "output_tokens": 0},
        {"input_tokens": 1, "output_tokens": None},
        {"input_tokens": 1, "output_tokens": 0, "input_token_details": {"cache_read": "bad"}},
        {"input_tokens": 1, "output_tokens": 0, "input_token_details": {"cache_creation": True}},
        {"input_tokens": 10, "output_tokens": 0, "input_token_details": []},
        {"input_tokens": 10, "output_tokens": 0, "input_token_details": False},
        {"input_tokens": 10, "output_tokens": 0, "input_token_details": 0},
    ],
)
async def test_invalid_measurements_are_unmetered_instead_of_fabricated(usage):
    meter = Meter(rates())
    await meter.on_llm_end(response(usage))
    assert meter.unmetered_calls == 1
    assert meter.total == 0


async def test_failed_call_preserves_known_charge_and_records_unknown_usage_safely(monkeypatch):
    from structlog.testing import capture_logs

    meter = Meter(rates())
    await meter.on_llm_end(response({"input_tokens": 10, "output_tokens": 0}))
    with capture_logs() as logs:
        await meter.on_llm_error(RuntimeError("private upstream payload"))
    assert meter.total == 1 and meter.units == 1
    assert meter.unmetered_calls == 1
    assert logs[0]["error_type"] == "RuntimeError"
    assert "private upstream payload" not in str(logs)


async def test_unknown_write_price_keeps_known_charges_and_marks_partial_measurement():
    meter = Meter(rates(cache_write_units_per_token=None))
    await meter.on_llm_end(
        response(
            {"input_tokens": 10, "output_tokens": 2, "input_token_details": {"cache_creation": 3}}
        )
    )
    assert meter.total == Decimal("1.1")
    assert meter.unmetered_calls == 1


async def test_started_call_without_terminal_callback_stays_unmetered_without_double_count():
    from uuid import uuid4

    meter = Meter(rates())
    first, second = uuid4(), uuid4()
    await meter.on_chat_model_start({}, [], run_id=first)
    await meter.on_chat_model_start({}, [], run_id=second)
    assert meter.unmetered_calls == 2
    await meter.on_llm_end(response({"input_tokens": 10, "output_tokens": 0}), run_id=first)
    assert meter.units == 1 and meter.unmetered_calls == 1
    await meter.on_llm_error(RuntimeError(), run_id=second)
    assert meter.unmetered_calls == 1 and not meter.pending_calls
