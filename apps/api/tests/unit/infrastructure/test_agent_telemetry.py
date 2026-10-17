from contextlib import aclosing

import pytest
import structlog
from ag_ui.core import RunErrorEvent, RunFinishedEvent, RunStartedEvent
from structlog.testing import capture_logs

from pycil.observability import ag_ui
from pycil.observability.ag_ui import observed_agent_events


@pytest.mark.parametrize(
    "terminal,outcome",
    [
        (RunFinishedEvent(thread_id="private-thread", run_id="private-run"), "succeeded"),
        (
            RunFinishedEvent(
                thread_id="t",
                run_id="r",
                outcome={
                    "type": "interrupt",
                    "interrupts": [{"id": "approval", "reason": "approval"}],
                },
            ),
            "interrupted",
        ),
        (RunFinishedEvent(thread_id="t", run_id="r", outcome={"type": "cancelled"}), "cancelled"),
        (RunErrorEvent(message="private-provider-output"), "failed"),
        (None, "failed"),
    ],
)
async def test_native_terminal_events_are_forwarded_and_measured(
    terminal, outcome, operation_metrics, monkeypatch
):
    async def source():
        if terminal is not None:
            yield terminal

    with capture_logs() as logs:
        monkeypatch.setattr(ag_ui, "logger", structlog.get_logger(__name__))
        received = [
            event async for event in observed_agent_events(source(), name="assistant_stream")
        ]
    assert received == ([] if terminal is None else [terminal])
    if received:
        assert received[0] is terminal
    points = operation_metrics()
    assert len(points) == 1 and points[0].count == 1
    assert points[0].attributes == {"operation": "assistant_stream", "outcome": outcome}
    assert len(logs) == 1 and logs[0]["outcome"] == outcome
    assert "private" not in str(logs)


async def test_error_event_remains_failed_even_if_followed_by_finish(operation_metrics):
    async def source():
        yield RunErrorEvent(message="private-provider-output")
        yield RunFinishedEvent(thread_id="t", run_id="r")

    _ = [event async for event in observed_agent_events(source(), name="assistant_stream")]
    assert operation_metrics()[0].attributes["outcome"] == "failed"


@pytest.mark.parametrize("close", [False, True])
async def test_disconnect_or_exception_closes_source_and_records_once(
    close, operation_metrics, monkeypatch
):
    cleaned = False

    async def source():
        nonlocal cleaned
        try:
            yield RunStartedEvent(thread_id="t", run_id="r")
            raise RuntimeError("private-provider-output")
        finally:
            cleaned = True

    with capture_logs() as logs:
        monkeypatch.setattr(ag_ui, "logger", structlog.get_logger(__name__))
        async with aclosing(observed_agent_events(source(), name="assistant_stream")) as events:
            await anext(events)
            if not close:
                with pytest.raises(RuntimeError, match="private-provider-output"):
                    await anext(events)
    assert cleaned
    points = operation_metrics()
    assert len(points) == 1 and points[0].count == 1
    assert points[0].attributes["outcome"] == ("cancelled" if close else "failed")
    assert "private" not in str(logs)
