from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from ag_ui.core import RunAgentInput
from ag_ui_langgraph.utils import langchain_messages_to_agui
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select, tuple_

from pycil.account.auth import UserId
from pycil.account.lifecycle import require_user
from pycil.app.dependencies import Config, Session
from pycil.app.pagination import decode, encode, page_limit, strict_query
from pycil.assistant import graph as agents
from pycil.assistant.conversations import delete_conversation, owned
from pycil.assistant.models import Conversation
from pycil.assistant.schemas import (
    AssistantModel,
    ConversationDetails,
    ConversationPage,
    ConversationView,
    CreateConversation,
)
from pycil.assistant.stream import prepare_turn
from pycil.infrastructure.observability import get_logger
from pycil.utils.orm import row_data

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/assistant", tags=["assistant"])


@router.get("/models", response_model=list[AssistantModel])
async def models(user: UserId, config: Config):
    return [
        {"id": m.id, "name": m.name, "vision": m.vision, "efforts": m.efforts}
        for m in config.product.assistant.models
    ]


@router.post("/conversations", status_code=201, response_model=ConversationView)
async def create(data: CreateConversation, user: UserId, session: Session):
    async with session.begin():
        await require_user(session, user)
        conversation = Conversation(user_id=user, title=data.title)
        session.add(conversation)
        await session.flush()
        logger.info(
            "conversation_created",
            conversation_id=str(conversation.id),
            user_id=str(user),
        )
        return row_data(conversation)


@router.get("/conversations", response_model=ConversationPage)
async def listing(
    request: Request,
    user: UserId,
    session: Session,
    config: Config,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int | None = Query(default=None, ge=1, le=100),
):
    strict_query(request, {"cursor", "limit"})
    limit = page_limit(limit, config)
    binding = {"kind": "conversations", "viewer": str(user)}
    seek, _ = decode(cursor, binding, ["time", "uuid"])
    query = select(Conversation).where(Conversation.user_id == user)
    if seek is not None:
        query = query.where(tuple_(Conversation.updated_at, Conversation.id) < tuple_(*seek))
    rows = (
        await session.scalars(
            query.order_by(Conversation.updated_at.desc(), Conversation.id.desc()).limit(limit + 1)
        )
    ).all()
    page = rows[:limit]
    return {
        "conversations": [row_data(row) for row in page],
        "next_cursor": (
            encode(binding, [page[-1].updated_at, page[-1].id]) if len(rows) > len(page) else None
        ),
    }


@router.get("/conversations/{identifier}", response_model=ConversationDetails)
async def state(identifier: UUID, user: UserId, session: Session, request: Request, config: Config):
    row = await owned(session, user, identifier)
    await session.commit()
    resources = request.app.state
    policy = next(
        m
        for m in config.product.assistant.models
        if m.id == config.product.assistant.defaults.model
    )
    async with agents.model(
        resources.deployment,
        policy,
        config.product.assistant.defaults.effort,
        config.runtime.assistant.llm_timeout_seconds,
    ) as selected:
        snapshot = await agents.graph(resources, user, config, selected).aget_state(
            {"configurable": {"thread_id": str(identifier)}}
        )
    return row_data(row) | {
        "state": {
            "messages": langchain_messages_to_agui(snapshot.values.get("messages", [])),
            "pending_approvals": [
                {"interrupt_id": interrupt.id, **interrupt.value}
                for task in snapshot.tasks
                for interrupt in task.interrupts
            ],
        }
    }


@router.delete("/conversations/{identifier}", status_code=204)
async def remove(identifier: UUID, user: UserId, request: Request, config: Config):
    await delete_conversation(
        request.app.state, user, identifier, lease_ttl=config.runtime.assistant.lease_ttl_seconds
    )
    return Response(status_code=204)


async def turn_events(data: RunAgentInput, user: UserId, request: Request, config: Config):
    async with prepare_turn(
        request.app.state, request.app.state.deployment, user, data, config
    ) as events:
        yield events


@router.post(
    ":run",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Native AG-UI events, including approval interrupts and run errors.",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
async def stream(events: Annotated[AsyncIterator[str], Depends(turn_events, scope="request")]):
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        # Next's compression middleware buffers small SSE chunks without no-transform.
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
