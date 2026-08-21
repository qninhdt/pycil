"""Async tasks survive an initial ARQ enqueue outage.

Also pins what happens to a kind with no handler. That case used to be silent: the
`if/elif` chain simply fell through, so the row stayed queued forever and the returned
`count` still claimed it had been reconciled. `question_pool` was exactly such a kind
before it was deleted, which is how it stayed in the codebase unnoticed.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from shared.tasks.contract import (
    JOB_NAME_FOR_KIND,
    TASK_KIND_GRADING,
    TASK_KIND_QUESTION_SUPPLY,
    TASK_KIND_WORD,
    GradingDispatch,
    SupplyDispatch,
    WordDispatch,
)

from pycil_worker.jobs.reconcile_async_tasks import reconcile_async_tasks


@asynccontextmanager
async def _session_factory():
    yield object()


class _Redis:
    def __init__(self) -> None:
        self.enqueued: list[tuple] = []

    async def enqueue_job(self, *args):
        self.enqueued.append(args)


def _patch_tasks(monkeypatch, tasks):
    from pycil.tasks.application import service as task_service

    async def list_reenqueueable(_session):
        return tasks

    monkeypatch.setattr(task_service, "list_reenqueueable_tasks", list_reenqueueable)


async def test_reconciliation_reenqueues_each_live_task_kind(monkeypatch):
    tasks = [
        SimpleNamespace(
            id=uuid4(),
            kind=TASK_KIND_WORD,
            dispatch=WordDispatch(query="run", owner_id="word-owner").to_dispatch(),
        ),
        SimpleNamespace(
            id=uuid4(),
            kind=TASK_KIND_GRADING,
            dispatch=GradingDispatch(owner_id="owner", response_id="response").to_dispatch(),
        ),
        SimpleNamespace(
            id=uuid4(),
            kind=TASK_KIND_QUESTION_SUPPLY,
            dispatch=SupplyDispatch(
                owner_id="supply-owner",
                session_id="abc123",
                round_index=2,
                demands=[(41, 1, 1)],
            ).to_dispatch(),
        ),
    ]
    redis = _Redis()
    _patch_tasks(monkeypatch, tasks)

    result = await reconcile_async_tasks(
        {"session_factory": _session_factory, "redis": redis}
    )

    assert result == {"status": "reconciled", "count": 3, "unhandled": 0}
    # `owner_id` travels with the re-enqueue so the retried job can still return the
    # inflight slot the original submission was charged.
    #
    # `question_supply` matters more than the other two, and for a reason specific to
    # it: the learner's client subscribes to that task and no longer re-calls `/next`
    # while waiting. So a supply row whose enqueue was lost is not a slow session but
    # a stopped one, and this branch is the entire backstop for that.
    assert redis.enqueued == [
        (JOB_NAME_FOR_KIND[TASK_KIND_WORD], str(tasks[0].id), "run", "word-owner"),
        (JOB_NAME_FOR_KIND[TASK_KIND_GRADING], str(tasks[1].id), "owner", "response"),
        (
            JOB_NAME_FOR_KIND[TASK_KIND_QUESTION_SUPPLY],
            str(tasks[2].id),
            "supply-owner",
            [[41, 1, 1]],
        ),
    ]


async def test_a_word_row_reenqueues_with_the_owner_that_was_charged(monkeypatch):
    """The re-enqueue must carry the owner, or the refund has nobody to credit.

    This used to assert the opposite — that a row without `owner_id` still
    recovered, passing None onward — as tolerance for rows written before the
    field existed. No such row was ever written. Both producers put `owner_id` in
    `dispatch` at submission, so reading it with `.get()` only turned a malformed
    row into a silently unrefunded slot.
    """
    tasks = [
        SimpleNamespace(
            id=uuid4(),
            kind=TASK_KIND_WORD,
            dispatch=WordDispatch(query="legacy", owner_id="word-owner").to_dispatch(),
        )
    ]
    redis = _Redis()
    _patch_tasks(monkeypatch, tasks)

    result = await reconcile_async_tasks(
        {"session_factory": _session_factory, "redis": redis}
    )

    assert result == {"status": "reconciled", "count": 1, "unhandled": 0}
    assert redis.enqueued == [
        (JOB_NAME_FOR_KIND[TASK_KIND_WORD], str(tasks[0].id), "legacy", "word-owner")
    ]


async def test_a_word_row_missing_its_owner_fails_loudly(monkeypatch):
    """A dispatch with no owner raises rather than re-enqueueing unrefundably.

    Deliberately pinning the blunt behaviour: `dispatch["owner_id"]` raises
    KeyError, and there is no per-task guard, so the batch aborts. That is worse
    than skipping the row and better than the `.get()` it replaced, which
    re-enqueued a job whose refund could never be credited to anyone.

    No producer can write such a row — both put `owner_id` in `dispatch` at
    submission — so this documents the blast radius if one ever does, rather than
    claiming the reconciler handles it gracefully. Making it a skip-and-report is
    a change to the reconciler's error contract, which belongs with the task
    dispatch work, not here.
    """
    tasks = [SimpleNamespace(id=uuid4(), kind=TASK_KIND_WORD, dispatch={"query": "no-owner"})]
    redis = _Redis()
    _patch_tasks(monkeypatch, tasks)

    with pytest.raises(KeyError):
        await reconcile_async_tasks({"session_factory": _session_factory, "redis": redis})

    assert redis.enqueued == [], "a row with no owner must not be re-enqueued"


async def test_a_kind_with_no_handler_is_counted_and_not_enqueued(monkeypatch):
    """The silence this replaces.

    An unrecoverable row must be visible in the result rather than inflating `count`,
    which previously reported every row as reconciled whether or not anything was
    enqueued for it.
    """
    tasks = [
        SimpleNamespace(
            id=uuid4(),
            kind=TASK_KIND_WORD,
            dispatch=WordDispatch(query="run", owner_id="o").to_dispatch(),
        ),
        SimpleNamespace(id=uuid4(), kind="something_removed", dispatch={}),
    ]
    redis = _Redis()
    _patch_tasks(monkeypatch, tasks)

    result = await reconcile_async_tasks(
        {"session_factory": _session_factory, "redis": redis}
    )

    assert result == {"status": "reconciled", "count": 1, "unhandled": 1}
    assert redis.enqueued == [
        (JOB_NAME_FOR_KIND[TASK_KIND_WORD], str(tasks[0].id), "run", "o")
    ]


async def test_an_unhandled_kind_does_not_stop_the_rest_of_the_batch(monkeypatch):
    """One unrecoverable row must not strand the recoverable ones behind it."""
    tasks = [
        SimpleNamespace(id=uuid4(), kind="gone", dispatch={}),
        SimpleNamespace(
            id=uuid4(),
            kind=TASK_KIND_WORD,
            dispatch=WordDispatch(query="after", owner_id="o").to_dispatch(),
        ),
    ]
    redis = _Redis()
    _patch_tasks(monkeypatch, tasks)

    result = await reconcile_async_tasks(
        {"session_factory": _session_factory, "redis": redis}
    )

    assert result["count"] == 1
    assert redis.enqueued == [
        (JOB_NAME_FOR_KIND[TASK_KIND_WORD], str(tasks[1].id), "after", "o")
    ]


async def test_question_pool_is_gone_and_would_now_be_reported(monkeypatch):
    """Regression guard on the deletion itself.

    If `question_pool` is ever reintroduced without a handler, this is the branch that
    says so instead of leaving the row queued indefinitely.
    """
    tasks = [
        SimpleNamespace(
            id=uuid4(),
            kind="question_pool",
            dispatch={"word_id": 7, "sense_id": 8},
        )
    ]
    redis = _Redis()
    _patch_tasks(monkeypatch, tasks)

    result = await reconcile_async_tasks(
        {"session_factory": _session_factory, "redis": redis}
    )

    assert result == {"status": "reconciled", "count": 0, "unhandled": 1}
    assert redis.enqueued == []
