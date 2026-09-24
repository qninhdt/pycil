"""Focused fixtures for durable assistant lifecycle tests."""

from datetime import UTC, datetime, timedelta

from pycil.assistant.application.persistence import retention_deadline
from pycil.assistant.infra.models import AssistantThread
from pycil.auth.models import User


async def create_user(session, email: str = "assistant-user@example.test") -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def create_thread(session, owner_id, title: str = "Assistant test") -> AssistantThread:
    thread = AssistantThread(
        owner_id=owner_id,
        title=title,
        retention_deadline=retention_deadline(),
    )
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    return thread


def expired_at() -> datetime:
    return datetime.now(UTC) - timedelta(seconds=1)
