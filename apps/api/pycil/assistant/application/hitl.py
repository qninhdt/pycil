"""Durable, single-winner approval state transitions and minimized audit trail."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.assistant.infra.models import ActionStatus, AssistantAction, AssistantActionAudit
from pycil.common.errors import ConflictError, NotFoundError
from pycil.config import settings
from pycil.db.session import async_session_factory
from pycil.hierarchy.infra.models import Node


def canonical_digest(arguments: dict) -> str:
    raw = json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_pending_action(
    session: AsyncSession,
    *,
    run_id: UUID,
    owner_id: UUID,
    tool: str,
    arguments: dict,
    checkpoint_version: str = "unknown",
    resource_generation: int | None = None,
) -> AssistantAction:
    action = AssistantAction(
        run_id=run_id,
        owner_id=owner_id,
        tool=tool,
        args_digest=canonical_digest(arguments),
        canonical_args=arguments,
        checkpoint_version=checkpoint_version,
        resource_generation=resource_generation,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.assistant_action_ttl_seconds),
        correlation_id=uuid4(),
    )
    session.add(action)
    await session.flush()
    session.add(
        AssistantActionAudit(
            action_id=action.id,
            actor_id=owner_id,
            decision="proposed",
            sanitized_digest=action.args_digest,
            correlation_id=action.correlation_id,
        )
    )
    await session.commit()
    await session.refresh(action)
    return action


async def claim_decision(
    session: AsyncSession, action_id: UUID, owner_id: UUID, decision: str
) -> AssistantAction:
    action = await session.scalar(
        select(AssistantAction).where(AssistantAction.id == action_id).with_for_update()
    )
    if action is None or action.owner_id != owner_id:
        raise NotFoundError("assistant_action_not_found")
    # A prior approved confirmation whose SSE body was never consumed may be
    # safely resumed from the same checkpoint; it has not executed a tool.
    if action.status in {ActionStatus.APPROVED, ActionStatus.EXECUTING} and decision == "approve":
        return action
    if action.status != ActionStatus.PENDING:
        raise ConflictError("assistant_action_already_resolved")
    if action.expires_at <= datetime.now(UTC):
        action.status = ActionStatus.EXPIRED
        await session.commit()
        raise ConflictError("assistant_action_expired")
    action.status = ActionStatus.APPROVED if decision == "approve" else ActionStatus.REJECTED
    session.add(
        AssistantActionAudit(
            action_id=action.id,
            actor_id=owner_id,
            decision=decision,
            sanitized_digest=action.args_digest,
            correlation_id=action.correlation_id,
        )
    )
    await session.commit()
    await session.refresh(action)
    return action


async def expire_pending_actions(session: AsyncSession) -> int:
    """Worker-safe conditional expiry. Approval and expiry contend on one row lock."""
    rows = await session.scalars(
        select(AssistantAction)
        .where(
            AssistantAction.status == ActionStatus.PENDING,
            AssistantAction.expires_at <= datetime.now(UTC),
        )
        .with_for_update(skip_locked=True)
    )
    expired = 0
    for action in rows:
        action.status = ActionStatus.EXPIRED
        expired += 1
    if expired:
        await session.commit()
    return expired


async def mark_executing(session: AsyncSession, action: AssistantAction) -> None:
    if action.status == ActionStatus.EXECUTING:
        return
    if action.status != ActionStatus.APPROVED:
        raise ConflictError("assistant_action_not_approved")
    action.status = ActionStatus.EXECUTING
    await session.commit()


async def finish_action(action_id: UUID, succeeded: bool) -> None:
    """Record one terminal execution result after the resumed graph completes."""
    async with async_session_factory() as session:
        action = await session.get(AssistantAction, action_id)
        if action is not None and action.status == ActionStatus.EXECUTING:
            action.status = ActionStatus.SUCCEEDED if succeeded else ActionStatus.FAILED
            action.result = {"status": action.status.value}
            session.add(
                AssistantActionAudit(
                    action_id=action.id,
                    actor_id=action.owner_id,
                    decision=action.status.value,
                    sanitized_digest=action.args_digest,
                    correlation_id=action.correlation_id,
                )
            )
            await session.commit()


async def validate_action_freshness(session: AsyncSession, action: AssistantAction) -> None:
    """Invalidate a proposal if its target was removed, transferred, or changed."""
    generations = action.canonical_args.get("_resource_generations", {})
    if not isinstance(generations, dict):
        return
    if not generations and action.resource_generation is not None:
        key = "node_id" if "node_id" in action.canonical_args else "deck_id"
        generations = {key: action.resource_generation}
    for key, generation in generations.items():
        raw_node_id = action.canonical_args.get(key)
        try:
            node_id = UUID(str(raw_node_id))
        except ValueError as exc:
            raise ConflictError("assistant_action_invalid_arguments") from exc
        node = await session.get(Node, node_id)
        if (
            node is None
            or node.deleted_at is not None
            or node.author_id != action.owner_id
            or node.structural_generation != generation
        ):
            action.status = ActionStatus.INVALIDATED
            session.add(
                AssistantActionAudit(
                    action_id=action.id,
                    actor_id=action.owner_id,
                    decision="invalidated",
                    sanitized_digest=action.args_digest,
                    correlation_id=action.correlation_id,
                )
            )
            await session.commit()
            raise ConflictError("assistant_action_stale")
