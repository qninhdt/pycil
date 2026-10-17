import asyncio
from contextlib import nullcontext

import pytest
import structlog

from pycil.observability import (
    OperationOutcome,
    bound_contextvars,
    get_logger,
    observe_operation,
)


@pytest.mark.parametrize(
    "error, outcome",
    [
        (None, OperationOutcome.SUCCEEDED),
        (ValueError("private payload"), OperationOutcome.FAILED),
        (asyncio.CancelledError(), OperationOutcome.CANCELLED),
    ],
)
def test_operation_preserves_failure_and_restores_correlation(error, outcome, operation_metrics):
    logger = get_logger(__name__)
    with structlog.testing.capture_logs(
        processors=[structlog.contextvars.merge_contextvars]
    ) as logs:
        with bound_contextvars(request_id="request", operation="parent"):
            expectation = pytest.raises(type(error)) if error is not None else nullcontext()
            with expectation as raised:
                with observe_operation(logger, "generation", word_id=7):
                    assert structlog.contextvars.get_contextvars()["request_id"] == "request"
                    if error is not None:
                        raise error
            if error is not None:
                assert raised.value is error
            assert structlog.contextvars.get_contextvars()["operation"] == "parent"
            assert "word_id" not in structlog.contextvars.get_contextvars()
    assert [event["event"] for event in logs] == ["operation_started", "operation_completed"]
    completed = logs[-1]
    assert completed["outcome"] == outcome
    assert completed["duration_ms"] >= 0
    assert completed["error_type"] == (type(error).__name__ if error is not None else None)
    assert completed["request_id"] == "request"
    assert completed["word_id"] == 7
    assert "private payload" not in str(logs)
    points = operation_metrics()
    assert len(points) == 1 and points[0].count == 1
    assert points[0].attributes == {"operation": "generation", "outcome": outcome.value}
    assert abs(points[0].sum * 1000 - completed["duration_ms"]) <= 0.0051
