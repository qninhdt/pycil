"""Private learning-session deliveries over shared question tasks."""


import pytest
from sqlalchemy import func, select

from pycil.auth.models import User
from pycil.tasks import service
from pycil.tasks.models import AsyncTaskDelivery

pytestmark = pytest.mark.asyncio


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _kwargs(owner_id, session_id: str, command_id: str) -> dict:
    return {
        "server_work_key": "question-pool:41:definition_mcq:v1:0",
        "owner_id": owner_id,
        "session_id": session_id,
        "sense_id": 41,
        "question_format": "definition_mcq",
        "command_id": command_id,
        "dispatch": {
            "word_id": 7,
            "sense_id": 41,
            "formats": ["definition_mcq"],
            "n": 1,
        },
    }


async def test_two_sessions_join_one_question_task_with_private_deliveries(session):
    owner = await _user(session, "question-deliveries@example.com")
    first = await service.submit_question_delivery(
        session, **_kwargs(owner.id, "session-a", "cmd-a")
    )
    second = await service.submit_question_delivery(
        session, **_kwargs(owner.id, "session-b", "cmd-b")
    )

    assert first.task_created
    assert not second.task_created
    assert first.task.id == second.task.id
    assert first.delivery.id != second.delivery.id
    assert first.delivery.session_id == "session-a"
    assert second.delivery.session_id == "session-b"
    assert await session.scalar(select(func.count()).select_from(AsyncTaskDelivery)) == 2


async def test_foreign_owner_cannot_load_private_delivery(session):
    owner = await _user(session, "delivery-owner@example.com")
    outsider = await _user(session, "delivery-outsider@example.com")
    submitted = await service.submit_question_delivery(
        session, **_kwargs(owner.id, "owner-session", "owner-command")
    )

    assert await service.get_question_delivery(
        session,
        submitted.delivery.id,
        session_id="owner-session",
        owner_id=outsider.id,
    ) is None


async def test_completion_before_second_session_subscribes_resolves_snapshot(session):
    first_owner = await _user(session, "delivery-first@example.com")
    second_owner = await _user(session, "delivery-second@example.com")
    first = await service.submit_question_delivery(
        session, **_kwargs(first_owner.id, "first-session", "first-command")
    )
    claimed = await service.claim_task(session, first.task.id, "worker")
    assert claimed is not None
    completed = await service.complete_question_task(
        session,
        first.task.id,
        lease_token=claimed.lease_token,
        lease_fence=claimed.lease_fence,
        result={"questions": [{"id": 99, "sense_id": 41, "format": "definition_mcq"}]},
    )
    assert completed is not None

    second = await service.submit_question_delivery(
        session, **_kwargs(second_owner.id, "second-session", "second-command")
    )
    assert second.task.id == first.task.id
    assert second.delivery.snapshot == {
        "taskId": str(first.task.id),
        "questionId": 99,
        "senseId": 41,
        "format": "definition_mcq",
    }


async def test_question_delivery_retry_returns_original_delivery(session):
    owner = await _user(session, "delivery-retry@example.com")
    first = await service.submit_question_delivery(
        session, **_kwargs(owner.id, "session", "retry-command")
    )
    replay = await service.submit_question_delivery(
        session, **_kwargs(owner.id, "session", "retry-command")
    )

    assert replay.task.id == first.task.id
    assert replay.delivery.id == first.delivery.id
    assert await session.scalar(select(func.count()).select_from(AsyncTaskDelivery)) == 1
