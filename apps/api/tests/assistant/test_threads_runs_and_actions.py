"""Owner scope, idempotent runs, and durable HITL transition tests."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from pycil.assistant.application import hierarchy_facade
from pycil.assistant.application import tools as assistant_tools
from pycil.assistant.application.hitl import (
    claim_decision,
    create_pending_action,
    expire_pending_actions,
    validate_action_freshness,
)
from pycil.assistant.application.persistence import create_or_load_run, require_owned_thread
from pycil.assistant.domain.context import AssistantContext
from pycil.assistant.infra.models import (
    ActionStatus,
    AssistantAction,
    AssistantActionAudit,
    RunStatus,
)
from pycil.common.errors import ConflictError, NotFoundError
from pycil.hierarchy.infra.models import Node, NodeType

from .conftest import create_run, create_thread, create_user, expired_at

pytestmark = pytest.mark.asyncio


async def test_thread_helper_does_not_leak_cross_owner_thread(session):
    owner = await create_user(session)
    intruder = await create_user(session, "intruder@example.test")
    thread = await create_thread(session, owner.id)

    with pytest.raises(NotFoundError, match="assistant_thread_not_found"):
        await require_owned_thread(session, thread.id, intruder.id)


async def test_duplicate_message_replays_same_run_and_active_run_is_rejected(session):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    message_id = uuid4()
    run, created = await create_or_load_run(
        session, thread_id=thread.id, owner_id=owner.id, client_message_id=message_id
    )
    assert created is True

    replay, created = await create_or_load_run(
        session, thread_id=thread.id, owner_id=owner.id, client_message_id=message_id
    )
    assert created is False
    assert replay.id == run.id

    with pytest.raises(ConflictError, match="assistant_thread_run_active"):
        await create_or_load_run(
            session, thread_id=thread.id, owner_id=owner.id, client_message_id=uuid4()
        )

    run.status = RunStatus.SUCCEEDED
    await session.commit()
    next_run, created = await create_or_load_run(
        session, thread_id=thread.id, owner_id=owner.id, client_message_id=uuid4()
    )
    assert created is True
    assert next_run.id != run.id


async def test_action_decisions_are_owner_scoped_single_winner_and_audited(session):
    owner = await create_user(session)
    intruder = await create_user(session, "intruder-action@example.test")
    thread = await create_thread(session, owner.id)
    run = await create_run(session, thread.id, owner.id, uuid4())
    action = await create_pending_action(
        session,
        run_id=run.id,
        owner_id=owner.id,
        tool="publish_node",
        arguments={"node_id": str(uuid4())},
        checkpoint_version=f"run:{run.id}",
    )

    with pytest.raises(NotFoundError, match="assistant_action_not_found"):
        await claim_decision(session, action.id, intruder.id, "approve")
    approved = await claim_decision(session, action.id, owner.id, "approve")
    assert approved.status == ActionStatus.APPROVED
    with pytest.raises(ConflictError, match="assistant_action_already_resolved"):
        await claim_decision(session, action.id, owner.id, "reject")

    audit = list(
        await session.scalars(
            select(AssistantActionAudit).where(AssistantActionAudit.action_id == action.id)
        )
    )
    assert [entry.decision for entry in audit] == ["proposed", "approve"]


async def test_action_reject_expiry_and_worker_expiry_are_terminal(session):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    run = await create_run(session, thread.id, owner.id, uuid4())
    rejected = await create_pending_action(
        session,
        run_id=run.id,
        owner_id=owner.id,
        tool="delete_node",
        arguments={},
        checkpoint_version=f"run:{run.id}",
    )
    assert (
        await claim_decision(session, rejected.id, owner.id, "reject")
    ).status == ActionStatus.REJECTED

    expired = await create_pending_action(
        session,
        run_id=run.id,
        owner_id=owner.id,
        tool="delete_node",
        arguments={},
        checkpoint_version=f"run:{run.id}",
    )
    expired.expires_at = expired_at()
    await session.commit()
    with pytest.raises(ConflictError, match="assistant_action_expired"):
        await claim_decision(session, expired.id, owner.id, "approve")
    await session.refresh(expired)
    assert expired.status == ActionStatus.EXPIRED

    worker_expired = await create_pending_action(
        session,
        run_id=run.id,
        owner_id=owner.id,
        tool="delete_node",
        arguments={},
        checkpoint_version=f"run:{run.id}",
    )
    worker_expired.expires_at = expired_at()
    await session.commit()
    assert await expire_pending_actions(session) == 1
    await session.refresh(worker_expired)
    assert worker_expired.status == ActionStatus.EXPIRED


async def test_stale_resource_generation_invalidates_pending_action(session):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    node = Node(author_id=owner.id, type=NodeType.FOLDER, name="original", structural_generation=4)
    session.add(node)
    await session.commit()
    await session.refresh(node)
    run = await create_run(session, thread.id, owner.id, uuid4())
    action = await create_pending_action(
        session,
        run_id=run.id,
        owner_id=owner.id,
        tool="publish_node",
        arguments={"node_id": str(node.id)},
        checkpoint_version=f"run:{run.id}",
        resource_generation=node.structural_generation,
    )
    node.structural_generation += 1
    await session.commit()

    with pytest.raises(ConflictError, match="assistant_action_stale"):
        await validate_action_freshness(session, action)
    await session.refresh(action)
    assert action.status == ActionStatus.INVALIDATED


async def test_sensitive_domain_write_and_action_result_share_one_transaction(session):
    """A crash/rollback cannot leave a committed delete without its action result."""
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    node = Node(author_id=owner.id, type=NodeType.FOLDER, name="atomic")
    session.add(node)
    await session.commit()
    run = await create_run(session, thread.id, owner.id, uuid4())
    action = await create_pending_action(
        session,
        run_id=run.id,
        owner_id=owner.id,
        tool="delete_node",
        arguments={"node_id": str(node.id)},
    )
    action.status = ActionStatus.EXECUTING
    await session.commit()
    node_id = node.id
    action_id = action.id

    await hierarchy_facade.delete_node(session, owner.id, node_id, commit=False)
    action.result = {"tool_result": "deleted"}
    action.status = ActionStatus.SUCCEEDED
    await session.rollback()

    recovered_node = await session.get(Node, node_id)
    recovered_action = await session.get(AssistantAction, action_id)
    assert recovered_node is not None and recovered_node.deleted_at is None
    assert recovered_action is not None and recovered_action.status == ActionStatus.EXECUTING


async def test_sensitive_execution_persists_minimized_success_audit(engine, session, monkeypatch):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    run = await create_run(session, thread.id, owner.id, uuid4())
    action = await create_pending_action(
        session,
        run_id=run.id,
        owner_id=owner.id,
        tool="delete_node",
        arguments={"node_id": str(uuid4())},
    )
    action.status = ActionStatus.EXECUTING
    await session.commit()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(assistant_tools, "async_session_factory", factory)

    class Runtime:
        context = AssistantContext(owner.id, owner.token_version, action.id)

    async def operation(_session, commit: bool) -> str:
        assert commit is False
        return "deleted"

    assert await assistant_tools._run_sensitive(Runtime(), operation) == "deleted"
    async with factory() as verify:
        audits = list(
            await verify.scalars(
                select(AssistantActionAudit)
                .where(AssistantActionAudit.action_id == action.id)
                .order_by(AssistantActionAudit.occurred_at)
            )
        )
    assert [audit.decision for audit in audits] == ["proposed", "succeeded"]
