"""Durable word-generation job lifecycle and owner isolation."""

from types import SimpleNamespace

import pytest

from pycil.auth import tokens
from pycil.auth.models import User
from pycil.content import router as content_router
from pycil.jobs import service
from pycil.jobs.models import JobStatus

pytestmark = pytest.mark.asyncio


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_job_lifecycle_is_fenced_and_owner_scoped(session):
    owner = await _user(session, "owner@x.co")
    stranger = await _user(session, "stranger@x.co")

    record = await service.create_generation(session, owner.id, "  Café   TEST ")
    assert record.status == JobStatus.QUEUED
    assert record.normalized_query == "café test"
    assert await service.get_generation(session, record.id, stranger.id) is None

    claimed = await service.claim_generation(session, record.id, "worker-a")
    assert claimed is not None
    assert claimed.status == JobStatus.RUNNING
    assert claimed.attempt == 1
    assert claimed.lease_token
    assert claimed.lease_fence == 1
    assert await service.claim_generation(session, record.id, "worker-b") is None

    assert (
        await service.complete_generation(
            session, record.id, "wrong-token", claimed.lease_fence, {"wordId": 10}
        )
        is None
    )
    completed = await service.complete_generation(
        session,
        record.id,
        claimed.lease_token,
        claimed.lease_fence,
        {"wordId": 10, "senseIds": [1, 2]},
    )
    assert completed is not None
    assert completed.status == JobStatus.SUCCEEDED
    assert completed.result == {"wordId": 10, "senseIds": [1, 2]}
    assert (
        await service.fail_generation(
            session, record.id, claimed.lease_token, claimed.lease_fence, "late_failure"
        )
        is None
    )


async def test_expired_lease_is_reclaimed_with_new_fence_and_failures_back_off(session):
    owner = await _user(session, "lease-owner@x.co")
    record = await service.create_generation(session, owner.id, "example")
    first = await service.claim_generation(session, record.id, "worker-a", lease_seconds=0)
    assert first is not None
    first_token, first_fence = first.lease_token, first.lease_fence

    second = await service.claim_generation(session, record.id, "worker-b")
    assert second is not None
    assert second.lease_fence == first_fence + 1
    assert (
        await service.complete_generation(
            session, record.id, first_token, first_fence, {"wordId": 1}
        )
        is None
    )

    retried = await service.fail_generation(
        session, record.id, second.lease_token, second.lease_fence, "generation_failed"
    )
    assert retried is not None
    assert retried.status == JobStatus.QUEUED
    assert retried.next_attempt_at is not None


async def test_idempotent_submission_does_not_charge_quota_twice(session, monkeypatch):
    owner = await _user(session, "quota-owner@x.co")
    charges = 0

    async def reserve(_redis, _owner_id):
        nonlocal charges
        charges += 1
        return True

    monkeypatch.setattr(service, "reserve_quota", reserve)
    first, created, allowed = await service.submit_generation(
        session, object(), owner.id, "example", "same-request"
    )
    assert created and allowed
    replay, created, allowed = await service.submit_generation(
        session, object(), owner.id, "changed text", "same-request"
    )
    assert allowed and not created
    assert replay.id == first.id
    assert charges == 1


async def test_generation_endpoint_returns_task_receipt_and_enqueues_once(
    client, session, monkeypatch
):
    owner = await _user(session, "endpoint-owner@x.co")

    class FakePool:
        calls: list[tuple[str, str, str, str]] = []

        async def enqueue_job(self, *args):
            self.calls.append(args)

    pool = FakePool()

    async def fake_pool():
        return pool

    monkeypatch.setattr(content_router, "get_arq_pool", fake_pool)
    owner_token, _ = tokens.sign_access(owner)
    response = await client.post(
        "/v1/word-generations",
        json={"query": "example"},
        headers={
            "Authorization": f"Bearer {owner_token}",
            "Idempotency-Key": "submit-example-1",
        },
    )
    assert response.status_code == 202
    task_id = response.json()["taskId"]
    assert pool.calls == [("generate_word_task", task_id, "example")]

    duplicate = await client.post(
        "/v1/word-generations",
        json={"query": "example"},
        headers={
            "Authorization": f"Bearer {owner_token}",
            "Idempotency-Key": "submit-example-1",
        },
    )
    assert duplicate.status_code == 202
    assert duplicate.json()["taskId"] == task_id
    assert len(pool.calls) == 1


async def test_word_search_exposes_only_stable_lexi_projection():
    class Client:
        async def search(self, query):
            assert query == "example"
            return [
                SimpleNamespace(
                    display="example",
                    entry_type="word",
                    score=0.9,
                    lexi_word_id=17,
                    cambridge_id=12,
                    gloss="an instance",
                )
            ]

    result = await content_router.search_words("example", Client())
    assert result[0].model_dump(by_alias=True) == {
        "display": "example",
        "entryType": "word",
        "score": 0.9,
        "wordId": 17,
        "cambridgeId": 12,
        "gloss": "an instance",
        "pos": None,
        "senses": [],
    }
