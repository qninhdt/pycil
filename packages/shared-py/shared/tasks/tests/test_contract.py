"""Round-trip behavior of the dispatch payloads and the job-name registry."""

import pytest

from shared.tasks.contract import (
    JOB_NAME_FOR_KIND,
    TASK_KIND_GRADING,
    TASK_KIND_QUESTION_SUPPLY,
    TASK_KIND_WORD,
    WORKER_HEARTBEAT_KEY,
    WORKER_HEARTBEAT_TTL_SECONDS,
    GradingDispatch,
    SupplyDispatch,
    WordDispatch,
)


def test_job_names_are_the_registered_handler_names():
    """These strings are arq routing keys, so a rename is a cross-service event.

    The registry is the definition; pinning the exact values here means an
    accidental rename fails this test instead of stranding queued jobs on a
    worker that no longer knows the name.
    """
    assert JOB_NAME_FOR_KIND[TASK_KIND_WORD] == "generate_word_task"
    assert JOB_NAME_FOR_KIND[TASK_KIND_GRADING] == "grade_answer_task"
    assert JOB_NAME_FOR_KIND[TASK_KIND_QUESTION_SUPPLY] == "prepare_questions_task"


def test_task_kinds_are_stored_wire_data():
    """Kinds live in `async_tasks.kind`; renaming one needs a migration."""
    assert TASK_KIND_WORD == "word"
    assert TASK_KIND_GRADING == "grading"
    assert TASK_KIND_QUESTION_SUPPLY == "question_supply"


def test_word_dispatch_round_trips_through_storage():
    dispatch = WordDispatch(query="serendipity", owner_id="user-1")
    assert dispatch.to_dispatch() == {"query": "serendipity", "owner_id": "user-1"}
    assert WordDispatch.from_dispatch(dispatch.to_dispatch()) == dispatch
    assert dispatch.job_args() == ("serendipity", "user-1")


def test_grading_dispatch_round_trips_through_storage():
    dispatch = GradingDispatch(owner_id="user-1", response_id="response-9")
    assert dispatch.to_dispatch() == {"owner_id": "user-1", "response_id": "response-9"}
    assert GradingDispatch.from_dispatch(dispatch.to_dispatch()) == dispatch
    assert dispatch.job_args() == ("user-1", "response-9")


def test_supply_dispatch_normalizes_demands_to_json_safe_lists():
    """Producers hold tuples; storage holds lists. Both parse back the same."""
    dispatch = SupplyDispatch(
        owner_id="user-1",
        session_id="abc123",
        round_index=2,
        demands=[(41, 1, 1)],
    )
    stored = dispatch.to_dispatch()
    assert stored == {
        "owner_id": "user-1",
        "session_id": "abc123",
        "round_index": 2,
        "demands": [[41, 1, 1]],
    }
    parsed = SupplyDispatch.from_dispatch(stored)
    # Tuple inputs normalize to lists in storage, so identity is asserted
    # through the canonical stored form rather than object equality.
    assert parsed.to_dispatch() == stored
    assert parsed.job_args() == ("user-1", [[41, 1, 1]])


def test_parsing_a_malformed_row_raises_key_error():
    """The reconciler's fail-loud contract starts at the parse itself."""
    with pytest.raises(KeyError):
        WordDispatch.from_dispatch({"query": "incomplete"})


def test_heartbeat_signal_is_the_shared_readiness_key():
    assert WORKER_HEARTBEAT_KEY == "worker:heartbeat"
    assert WORKER_HEARTBEAT_TTL_SECONDS == 90
