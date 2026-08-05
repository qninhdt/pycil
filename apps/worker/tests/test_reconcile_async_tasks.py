"""Async tasks survive an initial ARQ enqueue outage.

Also pins what happens to a kind with no handler. That case used to be silent: the
`if/elif` chain simply fell through, so the row stayed queued forever and the returned
`count` still claimed it had been reconciled. `question_pool` was exactly such a kind
before it was deleted, which is how it stayed in the codebase unnoticed.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

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
    from pycil.tasks import service as task_service

    async def list_reenqueueable(_session):
        return tasks

    monkeypatch.setattr(task_service, "list_reenqueueable_tasks", list_reenqueueable)


async def test_reconciliation_reenqueues_each_live_task_kind(monkeypatch):
    tasks = [
        SimpleNamespace(
            id=uuid4(),
            kind="word",
            dispatch={"query": "run", "owner_id": "word-owner"},
        ),
        SimpleNamespace(
            id=uuid4(),
            kind="grading",
            dispatch={"owner_id": "owner", "response_id": "response"},
        ),
    ]
    redis = _Redis()
    _patch_tasks(monkeypatch, tasks)

    result = await reconcile_async_tasks(
        {"session_factory": _session_factory, "redis": redis}
    )

    assert result == {"status": "reconciled", "count": 2, "unhandled": 0}
    # `owner_id` travels with the re-enqueue so the retried job can still return the
    # inflight slot the original submission was charged.
    assert redis.enqueued == [
        ("generate_word_task", str(tasks[0].id), "run", "word-owner"),
        ("grade_answer_task", str(tasks[1].id), "owner", "response"),
    ]


async def test_a_word_row_from_the_previous_release_is_still_reenqueued(monkeypatch):
    """A queued row written before `owner_id` was recorded must still recover.

    Reconciliation is precisely what runs against rows created by the previous
    release. Requiring `owner_id` here would strand them permanently, so the job
    passes None and settles the task without releasing a slot it cannot attribute.
    """
    tasks = [SimpleNamespace(id=uuid4(), kind="word", dispatch={"query": "legacy"})]
    redis = _Redis()
    _patch_tasks(monkeypatch, tasks)

    result = await reconcile_async_tasks(
        {"session_factory": _session_factory, "redis": redis}
    )

    assert result == {"status": "reconciled", "count": 1, "unhandled": 0}
    assert redis.enqueued == [("generate_word_task", str(tasks[0].id), "legacy", None)]


async def test_a_kind_with_no_handler_is_counted_and_not_enqueued(monkeypatch):
    """The silence this replaces.

    An unrecoverable row must be visible in the result rather than inflating `count`,
    which previously reported every row as reconciled whether or not anything was
    enqueued for it.
    """
    tasks = [
        SimpleNamespace(
            id=uuid4(), kind="word", dispatch={"query": "run", "owner_id": "o"}
        ),
        SimpleNamespace(id=uuid4(), kind="something_removed", dispatch={}),
    ]
    redis = _Redis()
    _patch_tasks(monkeypatch, tasks)

    result = await reconcile_async_tasks(
        {"session_factory": _session_factory, "redis": redis}
    )

    assert result == {"status": "reconciled", "count": 1, "unhandled": 1}
    assert redis.enqueued == [("generate_word_task", str(tasks[0].id), "run", "o")]


async def test_an_unhandled_kind_does_not_stop_the_rest_of_the_batch(monkeypatch):
    """One unrecoverable row must not strand the recoverable ones behind it."""
    tasks = [
        SimpleNamespace(id=uuid4(), kind="gone", dispatch={}),
        SimpleNamespace(
            id=uuid4(), kind="word", dispatch={"query": "after", "owner_id": "o"}
        ),
    ]
    redis = _Redis()
    _patch_tasks(monkeypatch, tasks)

    result = await reconcile_async_tasks(
        {"session_factory": _session_factory, "redis": redis}
    )

    assert result["count"] == 1
    assert redis.enqueued == [("generate_word_task", str(tasks[1].id), "after", "o")]


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
