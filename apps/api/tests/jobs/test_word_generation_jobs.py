"""Durable word-generation job lifecycle and owner isolation."""

import pytest

from pycil.auth import tokens
from pycil.auth.models import User
from pycil.content import router as content_router
from pycil.content.lexi_types import SearchResult
from pycil.jobs import service
from pycil.jobs.models import JobStatus

pytestmark = pytest.mark.asyncio


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_job_lifecycle_is_single_claim_and_owner_scoped(session):
    owner = await _user(session, "owner@x.co")
    stranger = await _user(session, "stranger@x.co")

    record = await service.create_generation(session, owner.id, "  Café   TEST ")
    assert record.status == JobStatus.QUEUED
    assert record.normalized_query == "café test"
    assert await service.get_generation(session, record.id, stranger.id) is None

    claimed = await service.mark_running(session, record.id)
    assert claimed is not None
    assert claimed.status == JobStatus.RUNNING
    assert claimed.attempt == 1
    assert await service.mark_running(session, record.id) is None

    completed = await service.mark_succeeded(
        session, record.id, {"wordId": 10, "senseIds": [1, 2]}
    )
    assert completed is not None
    assert completed.status == JobStatus.SUCCEEDED
    assert completed.result == {"wordId": 10, "senseIds": [1, 2]}
    assert await service.mark_failed(session, record.id, "late_failure") is None


async def test_generation_endpoint_enqueues_and_job_endpoint_hides_other_owner(
    client, session, monkeypatch
):
    owner = await _user(session, "endpoint-owner@x.co")
    stranger = await _user(session, "endpoint-stranger@x.co")

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
    job_id = response.json()["jobId"]
    assert response.json()["status"] == "queued"
    assert pool.calls == [("generate_word", str(owner.id), "example", job_id)]

    duplicate = await client.post(
        "/v1/word-generations",
        json={"query": "example"},
        headers={
            "Authorization": f"Bearer {owner_token}",
            "Idempotency-Key": "submit-example-1",
        },
    )
    assert duplicate.status_code == 202
    assert duplicate.json()["jobId"] == job_id
    assert len(pool.calls) == 1

    response = await client.get(
        f"/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {owner_token}"}
    )
    assert response.status_code == 200
    assert response.json()["query"] == "example"

    stranger_token, _ = tokens.sign_access(stranger)
    response = await client.get(
        f"/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {stranger_token}"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_word_search_exposes_only_stable_lexi_projection():
    class Client:
        async def search(self, query):
            assert query == "example"
            return [
                SearchResult(
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
    }
