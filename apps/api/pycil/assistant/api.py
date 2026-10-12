from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from ag_ui.core import RunAgentInput
from ag_ui_langgraph.utils import langchain_messages_to_agui
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select, tuple_

from pycil.account.auth import Actor
from pycil.account.lifecycle import require_user, row_data
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
from pycil.dependencies import Product, Session
from pycil.logging import get_logger
from pycil.pagination import decode, encode, page_limit, strict_query

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/assistant", tags=["assistant"])


@router.get("/models", response_model=list[AssistantModel])
async def models(user: Actor, config: Product):
    return [
        {"id": m.id, "name": m.name, "vision": m.vision, "efforts": m.efforts}
        for m in config.models
    ]


@router.post("/conversations", status_code=201, response_model=ConversationView)
async def create(data: CreateConversation, user: Actor, session: Session):
    async with session.begin():
        await require_user(session, user.id)
        conversation = Conversation(user_id=user.id, title=data.title)
        session.add(conversation)
        await session.flush()
        logger.info(
            "conversation_created",
            conversation_id=str(conversation.id),
            user_id=str(user.id),
        )
        return row_data(conversation)


@router.get("/conversations", response_model=ConversationPage)
async def listing(
    request: Request,
    user: Actor,
    session: Session,
    config: Product,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int | None = Query(default=None, ge=1, le=100),
):
    strict_query(request, {"cursor", "limit"})
    limit = page_limit(limit, config)
    binding = {"kind": "conversations", "viewer": str(user.id)}
    seek, _ = decode(cursor, binding, ["time", "uuid"])
    query = select(Conversation).where(Conversation.user_id == user.id)
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
async def state(identifier: UUID, user: Actor, session: Session, request: Request, config: Product):
    row = await owned(session, user.id, identifier)
    await session.commit()
    resources = request.app.state
    policy = next(m for m in config.models if m.id == config.assistant.default_model)
    async with agents.model(
        resources.deployment,
        policy,
        config.assistant.default_effort,
        config.assistant.llm_timeout_seconds,
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
async def remove(identifier: UUID, user: Actor, request: Request):
    await delete_conversation(request.app.state, user, identifier)
    return Response(status_code=204)


async def turn_events(data: RunAgentInput, user: Actor, request: Request, config: Product):
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
