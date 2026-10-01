"""The job status route: owner-scoped reads over the real ASGI stack.

A job receipt belongs to one learner. Another caller guessing an id must get the
same 404 an unknown id gets, so the route never confirms that someone else's work
exists. These drive the wired route through the app's own error handler rather than
calling the function directly, so the status codes and envelope are what a client
actually receives.
"""

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from pycil.account.auth import current_user
from pycil.account.schemas import CurrentUser
from pycil.jobs.receipts import STATUS_DONE, STATUS_QUEUED, receipt_key
from pycil.main import create_app

pytestmark = pytest.mark.asyncio


def _actor(user_id) -> CurrentUser:
    return CurrentUser(id=user_id, email="learner@example.test")


@pytest_asyncio.fixture
async def owner_client():
    """A client whose caller is a known owner, plus the raw Redis under test."""
    app = create_app()
    owner_id = uuid4()

    async def identity() -> CurrentUser:
        return _actor(owner_id)

    app.dependency_overrides[current_user] = identity
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, owner_id


async def _receipt(fake_redis, *, owner_id, status=STATUS_QUEUED, **extra):
    import json

    job_id = str(uuid4())
    payload = {
        "id": job_id,
        "kind": "word",
        "owner_id": str(owner_id),
        "status": status,
        "result": None,
        "errorCode": None,
        **extra,
    }
    await fake_redis.set(receipt_key(job_id), json.dumps(payload))
    return job_id


async def test_the_owner_reads_their_own_job(owner_client, fake_redis):
    client, owner_id = owner_client
    job_id = await _receipt(fake_redis, owner_id=owner_id, status=STATUS_DONE, result={"wordId": 7})

    response = await client.get(f"/v1/jobs/{job_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["jobId"] == job_id
    assert body["kind"] == "word"
    assert body["status"] == STATUS_DONE
    assert body["result"] == {"wordId": 7}


async def test_another_learner_gets_an_indistinguishable_404(owner_client, fake_redis):
    """Existence must not leak: a stranger's 404 matches an unknown id's exactly."""
    client, _owner_id = owner_client
    someone_else = uuid4()
    job_id = await _receipt(fake_redis, owner_id=someone_else)

    stranger = await client.get(f"/v1/jobs/{job_id}")
    unknown = await client.get(f"/v1/jobs/{uuid4()}")

    assert stranger.status_code == 404
    assert unknown.status_code == 404
    assert stranger.json()["code"] == unknown.json()["code"] == "job_not_found"


async def test_an_expired_receipt_is_not_found(owner_client, fake_redis):
    """A missing receipt tells the client to retry, not that the work succeeded."""
    client, _owner_id = owner_client
    response = await client.get(f"/v1/jobs/{uuid4()}")
    assert response.status_code == 404


async def test_an_unexpected_status_is_reported_as_failed(owner_client, fake_redis):
    """An internal state must not become a new client contract by being echoed."""
    client, owner_id = owner_client
    job_id = await _receipt(fake_redis, owner_id=owner_id, status="something_new")

    response = await client.get(f"/v1/jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"


async def test_an_anonymous_caller_cannot_read_a_job(fake_redis):
    """A receipt carries one learner's result, so the route requires a caller."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/v1/jobs/{uuid4()}")

    assert response.status_code == 401
