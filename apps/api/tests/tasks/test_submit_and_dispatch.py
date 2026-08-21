"""The submit-and-dispatch choreography, pinned at its single home.

Every producer used to carry its own copy of reserve → submit → release →
best-effort enqueue, and the copies had already drifted in error-handling shape.
These tests pin the four properties each copy used to restate separately:

- a created task is enqueued under the registry's job name with the payload's
  handler arguments;
- joining existing work enqueues nothing and gives the reservation back;
- a failed submission gives the reservation back and propagates;
- a lost enqueue leaves the committed row (with its dispatch payload) for the
  reconciler.
"""

import uuid

import pytest

from pycil.auth.models import User
from pycil.tasks.application import dispatch
from pycil.tasks.domain.vocabulary import JOB_NAME_FOR_KIND, TASK_KIND_WORD, WordDispatch
from pycil.tasks.domain.work_keys import word_work_key
from pycil.tasks.infra.models import AsyncTask

pytestmark = pytest.mark.asyncio


class _Pool:
    """Records what was enqueued, so a missing or duplicate job is visible."""

    def __init__(self) -> None:
        self.jobs: list[tuple] = []

    async def enqueue_job(self, *args):
        self.jobs.append(args)


@pytest.fixture
def pool(monkeypatch) -> _Pool:
    recorder = _Pool()

    async def get_pool():
        return recorder

    monkeypatch.setattr(dispatch, "get_arq_pool", get_pool)
    return recorder


async def _owner(session) -> uuid.UUID:
    """A real user row: the interest holds a foreign key to it."""
    user = User(email=f"dispatch-{uuid.uuid4().hex[:8]}@example.com")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user.id


def _word_request(owner_id: uuid.UUID, *, command_id: str = "cmd-1") -> dict:
    return {
        "kind": TASK_KIND_WORD,
        "server_work_key": word_work_key("serendipity", "fingerprint"),
        "requester_id": owner_id,
        "command_kind": "word.generate",
        "command_id": command_id,
        "provenance": "word-search",
        "dispatch": WordDispatch(query="serendipity", owner_id=str(owner_id)),
    }


async def test_a_created_task_is_enqueued_under_the_registered_job_name(session, pool):
    owner_id = await _owner(session)

    submission = await dispatch.submit_and_dispatch(session, **_word_request(owner_id))

    assert submission.task_created is True
    assert pool.jobs == [
        (
            JOB_NAME_FOR_KIND[TASK_KIND_WORD],
            str(submission.task.id),
            "serendipity",
            str(owner_id),
        )
    ]


async def test_a_joined_task_enqueues_nothing_and_releases_the_reservation(session, pool):
    owner_id = await _owner(session)
    released: list[bool] = []

    async def release():
        released.append(True)

    first = await dispatch.submit_and_dispatch(
        session, release_reservation=release, **_word_request(owner_id)
    )
    second = await dispatch.submit_and_dispatch(
        session, release_reservation=release, **_word_request(owner_id, command_id="cmd-2")
    )

    assert first.task_created is True
    assert second.task_created is False
    # Only the join gave a slot back: the creator's charge is durably spent.
    assert released == [True]
    assert len(pool.jobs) == 1


async def test_a_failed_submission_releases_the_reservation_and_propagates(
    session, pool, monkeypatch
):
    owner_id = await _owner(session)
    released: list[bool] = []

    async def release():
        released.append(True)

    async def explode(*_args, **_kwargs):
        raise RuntimeError("submission failed")

    monkeypatch.setattr(dispatch.task_service, "submit_or_join", explode)

    with pytest.raises(RuntimeError, match="submission failed"):
        await dispatch.submit_and_dispatch(
            session, release_reservation=release, **_word_request(owner_id)
        )

    assert released == [True]
    assert pool.jobs == []


async def test_a_failed_submission_without_a_hook_still_propagates(session, pool, monkeypatch):
    """Producers whose charge is spent once their row is durable pass no hook."""
    owner_id = await _owner(session)

    async def explode(*_args, **_kwargs):
        raise RuntimeError("submission failed")

    monkeypatch.setattr(dispatch.task_service, "submit_or_join", explode)

    with pytest.raises(RuntimeError, match="submission failed"):
        await dispatch.submit_and_dispatch(session, **_word_request(owner_id))

    assert pool.jobs == []


async def test_a_lost_enqueue_leaves_the_committed_task_for_the_reconciler(
    session, monkeypatch
):
    owner_id = await _owner(session)

    async def broken_pool():
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(dispatch, "get_arq_pool", broken_pool)

    submission = await dispatch.submit_and_dispatch(session, **_word_request(owner_id))

    task = await session.get(AsyncTask, submission.task.id)
    assert task is not None, "the enqueue failure must not take the task with it"
    assert task.dispatch == WordDispatch(
        query="serendipity", owner_id=str(owner_id)
    ).to_dispatch()
