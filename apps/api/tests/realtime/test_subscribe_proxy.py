"""Durable SSE subscribe-proxy authorization and snapshot recovery."""

from datetime import UTC, datetime

import pytest

from pycil.auth.models import User
from pycil.realtime.subscriptions import SubscribeProxyRequest, authorize_subscription
from pycil.tasks import service

pytestmark = pytest.mark.asyncio


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _task(session, user: User):
    return await service.submit_or_join(
        session,
        kind="grading",
        server_work_key="grading:response-1",
        requester_id=user.id,
        command_kind="grading.submit",
        command_id="command-1",
        provenance="response-owner",
    )


def _request(user: User, task_id, **meta) -> SubscribeProxyRequest:
    return SubscribeProxyRequest(
        user=str(user.id),
        channel=f"async:{task_id}",
        meta={
            "tokenVersion": user.token_version,
            "expiresAt": int(datetime.now(UTC).timestamp()) + 60,
            **meta,
        },
    )


async def test_subscribe_returns_current_persisted_snapshot(session):
    user = await _user(session, "snapshot-subscribe@example.com")
    submission = await _task(session, user)

    result = await authorize_subscription(session, _request(user, submission.task.id))

    assert result["result"]["data"] == {
        "schema": "async-task.v1",
        "eventId": result["result"]["data"]["eventId"],
        "taskId": str(submission.task.id),
        "kind": "grading",
        "status": "queued",
        "version": 1,
        "result": None,
        "errorCode": None,
    }


async def test_subscribe_rejects_foreign_or_revoked_interest(session):
    owner = await _user(session, "owner-subscribe@example.com")
    outsider = await _user(session, "outsider-subscribe@example.com")
    submission = await _task(session, owner)

    assert await authorize_subscription(session, _request(outsider, submission.task.id)) == {
        "error": {"code": 103, "message": "permission denied"}
    }
    submission.interest.revoked_at = datetime.now(UTC)
    await session.commit()
    assert await authorize_subscription(session, _request(owner, submission.task.id)) == {
        "error": {"code": 103, "message": "permission denied"}
    }


async def test_subscribe_rejects_bad_channel_token_version_and_expiry(session):
    user = await _user(session, "invalid-subscribe@example.com")
    submission = await _task(session, user)

    result = await authorize_subscription(
        session, _request(user, submission.task.id, tokenVersion=99)
    )
    assert result == {
        "error": {"code": 103, "message": "permission denied"}
    }
    assert await authorize_subscription(
        session,
        SubscribeProxyRequest(
            user=str(user.id), channel="async:not-a-uuid", meta={"tokenVersion": 0, "expiresAt": 1}
        ),
    ) == {"error": {"code": 103, "message": "permission denied"}}
