from datetime import datetime
from uuid import UUID

from ag_ui.core import RunAgentInput
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, tuple_

from pycil.account.auth import Actor
from pycil.account.lifecycle import require_user, row_data
from pycil.assistant.conversations import delete_conversation, owned
from pycil.assistant.models import Conversation
from pycil.assistant.stream import prepare_turn
from pycil.dependencies import Product, Session
from pycil.http import Problem

router = APIRouter(prefix="/v1/assistant", tags=["assistant"])


class CreateConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=255)


@router.get("/models")
async def models(user: Actor, config: Product):
    return [
        {"id": m.id, "name": m.name, "vision": m.vision, "efforts": m.efforts}
        for m in config.models
    ]


@router.post("/conversations", status_code=201)
async def create(data: CreateConversation, user: Actor, session: Session):
    async with session.begin():
        await require_user(session, user.id)
        conversation = Conversation(user_id=user.id, title=data.title)
        session.add(conversation)
        await session.flush()
        return row_data(conversation)


@router.get("/conversations")
async def listing(
    user: Actor,
    session: Session,
    config: Product,
    after_updated_at: datetime | None = None,
    after_id: UUID | None = None,
):
    query = select(Conversation).where(Conversation.user_id == user.id)
    if (after_updated_at is None) != (after_id is None):
        raise Problem(422, "invalid_cursor")
    if after_updated_at is not None:
        if after_updated_at.utcoffset() is None:
            raise Problem(422, "invalid_cursor")
        query = query.where(
            tuple_(Conversation.updated_at, Conversation.id) < tuple_(after_updated_at, after_id)
        )
    rows = (
        await session.scalars(
            query.order_by(Conversation.updated_at.desc(), Conversation.id.desc()).limit(
                config.library.page_size + 1
            )
        )
    ).all()
    page = rows[: config.library.page_size]
    return {
        "conversations": [row_data(row) for row in page],
        "next_after": (
            {"updated_at": page[-1].updated_at, "id": page[-1].id}
            if len(rows) > len(page)
            else None
        ),
    }


@router.get("/conversations/{identifier}")
async def state(identifier: UUID, user: Actor, session: Session, request: Request):
    row = await owned(session, user.id, identifier)
    await session.commit()
    checkpoint = await AsyncPostgresSaver(request.app.state.checkpoint_pool).aget(
        {"configurable": {"thread_id": str(identifier)}}
    )
    return row_data(row) | {"state": checkpoint}


@router.delete("/conversations/{identifier}", status_code=204)
async def remove(identifier: UUID, user: Actor, request: Request):
    await delete_conversation(request.app.state, user, identifier)
    return Response(status_code=204)


@router.post("")
async def stream(data: RunAgentInput, user: Actor, request: Request, config: Product):
    return TurnResponse(request, user, data, config)


class TurnResponse(StreamingResponse):
    """Acquire/release turn resources around ASGI streaming, including send failure."""

    def __init__(self, request, user, data, config):
        super().__init__(
            iter(()), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )
        self.request, self.user, self.data, self.config = request, user, data, config

    async def __call__(self, scope, receive, send):
        async with prepare_turn(
            self.request.app.state,
            self.request.app.state.deployment,
            self.user,
            self.data,
            self.config,
        ) as events:
            self.body_iterator = events
            await super().__call__(scope, receive, send)
