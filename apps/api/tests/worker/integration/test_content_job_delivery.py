"""Best-effort background job receipt contract."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import BackgroundTasks

from pycil.jobs.contracts import TASK_KIND_WORD
from pycil.jobs.receipts import (
    JOB_STALE_SECONDS,
    STATUS_DONE,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_RUNNING,
    enqueue_job,
    read_receipt,
    receipt_key,
    update_job_status,
)

pytestmark = pytest.mark.asyncio


async def test_accepting_work_records_receipt_and_attaches_a_post_response_task(fake_redis):
    tasks = BackgroundTasks()
    job_id = await enqueue_job(fake_redis, tasks, TASK_KIND_WORD, {"query": "hello"}, "owner")
    receipt = await read_receipt(fake_redis, job_id)
    assert receipt["status"] == "queued"
    assert receipt["owner_id"] == "owner"
    assert len(tasks.tasks) == 1
    assert tasks.tasks[0].args == (job_id, TASK_KIND_WORD, {"query": "hello"})


async def test_unknown_kind_does_not_create_receipt(fake_redis):
    with pytest.raises(ValueError, match="unknown_job_kind"):
        await enqueue_job(fake_redis, BackgroundTasks(), "unknown", {}, "owner")
    assert await fake_redis.keys("pycil:job:*") == []


async def test_background_callback_runs_after_response_and_finishes(fake_redis, monkeypatch):
    from pycil.jobs import runner

    class _Lexicon:
        @classmethod
        def from_settings(cls):
            return cls()

        async def close(self):
            pass

    async def generate(_context, payload):
        assert payload == {"query": "hello"}
        return {"wordId": 12}

    monkeypatch.setattr(runner, "Lexicon", _Lexicon)
    monkeypatch.setattr(runner.Redis, "from_url", lambda *a, **kw: fake_redis)
    monkeypatch.setattr(runner, "create_lexicon_reader", lambda _lexicon: object())
    monkeypatch.setattr(runner, "create_lexicon_worker_engine", lambda _lexicon: object())
    monkeypatch.setattr(runner, "generate_word", generate)
    tasks = BackgroundTasks()
    job_id = await enqueue_job(fake_redis, tasks, TASK_KIND_WORD, {"query": "hello"}, "owner")
    assert (await read_receipt(fake_redis, job_id))["status"] == "queued"
    await tasks()
    receipt = await read_receipt(fake_redis, job_id)
    assert receipt["status"] == STATUS_DONE
    assert receipt["result"] == {"wordId": 12}


async def test_transitions_preserve_owner_and_result(fake_redis):
    job_id = await enqueue_job(fake_redis, BackgroundTasks(), TASK_KIND_WORD, {}, "owner")
    await update_job_status(fake_redis, job_id, STATUS_RUNNING)
    await update_job_status(fake_redis, job_id, STATUS_DONE, result={"wordId": 7})
    receipt = await read_receipt(fake_redis, job_id)
    assert receipt["owner_id"] == "owner"
    assert receipt["result"] == {"wordId": 7}
    assert receipt["finishedAt"]
    await update_job_status(fake_redis, job_id, STATUS_FAILED, error="late_failure")
    assert (await read_receipt(fake_redis, job_id))["status"] == STATUS_DONE


async def test_abandoned_receipt_expires_without_a_scheduler(fake_redis):
    job_id = await enqueue_job(fake_redis, BackgroundTasks(), TASK_KIND_WORD, {}, "owner")
    raw = json.loads(await fake_redis.get(receipt_key(job_id)))
    raw["createdAt"] = (datetime.now(UTC) - timedelta(seconds=JOB_STALE_SECONDS + 1)).isoformat()
    await fake_redis.set(receipt_key(job_id), json.dumps(raw))
    assert (await read_receipt(fake_redis, job_id))["status"] == STATUS_EXPIRED
    await update_job_status(fake_redis, job_id, STATUS_DONE, result={"wordId": 7})
    assert (await read_receipt(fake_redis, job_id))["status"] == STATUS_EXPIRED
