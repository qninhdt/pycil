"""Chat-with-AI HTTP API: sessions + messages + SSE stream stub."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.services import chat_service


router = APIRouter(prefix="/chat", tags=["chat"])


class CreateSessionBody(BaseModel):
    deck_id: UUID | None = None


class SendMessageBody(BaseModel):
    content: str


@router.post("/sessions")
async def create_session(
    body: CreateSessionBody, user: UserDep, session: SessionDep
) -> dict:
    sid = await chat_service.create_session(
        session, user_id=user.id, deck_id=body.deck_id
    )
    return {"session_id": str(sid)}


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: UUID, user: UserDep, session: SessionDep
) -> dict:
    s = await chat_service.get_session(
        session, session_id=session_id, user_id=user.id
    )
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session_not_found")
    return s


@router.get("/sessions/{session_id}/messages")
async def list_messages(
    session_id: UUID, user: UserDep, session: SessionDep
) -> dict:
    msgs = await chat_service.get_messages(
        session, session_id=session_id, user_id=user.id
    )
    return {"messages": msgs}


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: UUID,
    body: SendMessageBody,
    user: UserDep,
    session: SessionDep,
) -> dict:
    s = await chat_service.get_session(
        session, session_id=session_id, user_id=user.id
    )
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session_not_found")
    if chat_service.is_input_capped(s["total_input_tokens"]):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "session_input_capped")
    msg_id = await chat_service.append_message(
        session, session_id=session_id, role="user", content=body.content
    )
    return {"message_id": str(msg_id)}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: UUID, user: UserDep, session: SessionDep
) -> dict:
    result = await session.execute(
        text(
            "DELETE FROM chat_sessions WHERE id = :sid AND user_id = :uid"
        ),
        {"sid": session_id, "uid": user.id},
    )
    await session.commit()
    return {"deleted": int(getattr(result, "rowcount", 0) or 0)}
