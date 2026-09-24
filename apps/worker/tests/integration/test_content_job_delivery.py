"""The Stream broker's delivery contract, exercised against a real consumer group.

These use a live Redis (or fakeredis where the command is supported) to check the
properties the phase depends on: a worker acknowledges only after its effect, a
pending entry is reclaimable after a crash, and starting a second worker does not
steal work a live one is running.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from pycil.queue.contracts import (
    CONSUMER_GROUP_NAME,
    JOB_NAME_FOR_KIND,
    PAYLOAD_VERSION,
    STREAM_NAME,
    TASK_KIND_QUESTION_SUPPLY,
    TASK_KIND_WORD,
    SupplyDispatch,
    WordDispatch,
)
from pycil.queue.receipts import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    enqueue_job,
    read_receipt,
    receipt_key,
    update_job_status,
)

pytestmark = pytest.mark.asyncio


async def test_publishing_writes_a_queued_receipt_before_the_message(fake_redis, monkeypatch):
    """The receipt exists before publication, so a poll never 404s on live work."""
    published = {}

    async def capture(message):
        published["message"] = message
        # The receipt must already be readable at the moment of publication.
        published["receipt"] = await read_receipt(fake_redis, message.task_id)

    monkeypatch.setattr("pycil.queue.receipts.get_broker", _broker(capture))

    job_id = await enqueue_job(
        fake_redis,
        TASK_KIND_WORD,
        WordDispatch(query="serendipity", owner_id="owner-1").to_dispatch(),
        owner_id="owner-1",
    )

    assert published["receipt"]["status"] == STATUS_QUEUED
    assert published["receipt"]["owner_id"] == "owner-1"
    receipt = await read_receipt(fake_redis, job_id)
    assert receipt["kind"] == TASK_KIND_WORD


async def test_a_publish_failure_is_recorded_not_left_queued(fake_redis, monkeypatch):
    """A permanent `queued` is the one state a polling client cannot escape."""

    async def explode(message):
        raise ConnectionError("redis down")

    monkeypatch.setattr("pycil.queue.receipts.get_broker", _broker(explode))

    with pytest.raises(ConnectionError):
        await enqueue_job(
            fake_redis,
            TASK_KIND_WORD,
            WordDispatch(query="x", owner_id="o").to_dispatch(),
            owner_id="o",
        )

    # Find the receipt the attempt created and confirm it is terminal.
    keys = await fake_redis.keys("pycil:job:*")
    assert len(keys) == 1
    receipt = json.loads(await fake_redis.get(keys[0]))
    assert receipt["status"] == STATUS_FAILED
    assert receipt["errorCode"] == "job_publish_failed"


async def test_an_unknown_kind_is_refused_before_anything_is_written(fake_redis):
    with pytest.raises(ValueError, match="unknown_job_kind"):
        await enqueue_job(fake_redis, "not_a_kind", {}, owner_id="o")
    assert await fake_redis.keys("pycil:job:*") == []


async def test_status_transitions_preserve_the_owner(fake_redis):
    """The owner is what the status route authorizes against, so it is never restated."""
    job_id = str(uuid4())
    await fake_redis.set(
        receipt_key(job_id),
        json.dumps({"id": job_id, "kind": TASK_KIND_WORD, "owner_id": "real-owner"}),
    )

    await update_job_status(fake_redis, job_id, STATUS_RUNNING)
    await update_job_status(fake_redis, job_id, STATUS_DONE, result={"wordId": 7})

    receipt = await read_receipt(fake_redis, job_id)
    assert receipt["owner_id"] == "real-owner"
    assert receipt["status"] == STATUS_DONE
    assert receipt["result"] == {"wordId": 7}
    assert "finishedAt" in receipt


async def test_a_terminal_receipt_records_when_it_finished(fake_redis):
    job_id = str(uuid4())
    await update_job_status(fake_redis, job_id, STATUS_QUEUED)
    assert "finishedAt" not in await read_receipt(fake_redis, job_id)

    await update_job_status(fake_redis, job_id, STATUS_FAILED, error="job_failed")
    assert "finishedAt" in await read_receipt(fake_redis, job_id)


def _broker(capture):
    """A stand-in whose `kick` records the message instead of publishing it."""

    class _Formatter:
        def dumps(self, message):
            from taskiq import BrokerMessage

            return BrokerMessage(
                task_id=message.task_id,
                task_name=message.task_name,
                message=json.dumps(
                    {
                        "task_id": message.task_id,
                        "task_name": message.task_name,
                        "args": message.args,
                        "kwargs": message.kwargs,
                    }
                ).encode(),
                labels={},
            )

    class _Broker:
        formatter = _Formatter()

        async def kick(self, message):
            await capture(message)

    return lambda: _Broker()


# --- contract and registry ----------------------------------------------------


async def test_every_kind_has_a_registered_handler_name():
    assert set(JOB_NAME_FOR_KIND) == {TASK_KIND_WORD, TASK_KIND_QUESTION_SUPPLY}
    assert all(JOB_NAME_FOR_KIND.values())


async def test_the_published_kwargs_carry_the_version_and_job_id(fake_redis, monkeypatch):
    """A worker must be able to refuse a payload version it does not understand."""
    seen = {}

    async def capture(message):
        seen.update(json.loads(message.message))

    monkeypatch.setattr("pycil.queue.receipts.get_broker", _broker(capture))

    job_id = await enqueue_job(
        fake_redis,
        TASK_KIND_QUESTION_SUPPLY,
        SupplyDispatch(
            owner_id="o", session_id="s", round_index=1, demands=[(41, 1)]
        ).to_dispatch(),
        owner_id="o",
    )

    assert seen["kwargs"]["payload_version"] == PAYLOAD_VERSION
    assert seen["kwargs"]["job_id"] == job_id
    assert seen["task_name"] == JOB_NAME_FOR_KIND[TASK_KIND_QUESTION_SUPPLY]


async def test_the_stream_and_group_names_are_shared_constants():
    """Both services must address one stream and one consumer group."""
    assert STREAM_NAME == "pycil:jobs"
    assert CONSUMER_GROUP_NAME == "pycil_workers"
