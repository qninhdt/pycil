"""Chat-with-AI HTTP API: sessions + messages + SSE stream."""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.db import ChatSession, DeckDefinition, Definition, Term

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
    result = await session.exec(
        delete(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user.id,
        )
    )
    await session.commit()
    return {"deleted": int(getattr(result, "rowcount", 0) or 0)}


async def _chat_stream(session_id: UUID, user_id: UUID):
    """Real SSE stream of LLM tokens with deck-grounded system prompt."""
    from pycil_core.db import get_engine
    from pycil_core.services import llm_streaming

    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as s:
        history = await chat_service.get_messages(
            s, session_id=session_id, user_id=user_id, limit=20
        )
        deck_terms = (
            await s.exec(
                select(Term.value, Definition.canonical_meaning)
                .select_from(ChatSession)
                .join(DeckDefinition, DeckDefinition.deck_id == ChatSession.deck_id)
                .join(Definition, Definition.id == DeckDefinition.definition_id)
                .join(Term, Term.id == Definition.term_id)
                .where(ChatSession.id == session_id)
                .limit(50)
            )
        ).all()

    system = "You are a concise vocabulary tutor."
    if deck_terms:
        lines = "\n".join(
            f"- {r.value}: {r.canonical_meaning or '(no canonical)'}"
            for r in deck_terms
        )
        system += f"\n\nUser's deck terms:\n{lines}"

    messages: list[dict] = [{"role": "system", "content": system}]
    for m in history:
        if m["role"] in ("user", "assistant"):
            messages.append({"role": m["role"], "content": m["content"]})

    yield f"event: status\ndata: {json.dumps({'session_id': str(session_id)})}\n\n".encode()

    buf: list[str] = []
    async for frame in llm_streaming.stream_chat(messages):
        if frame.get("kind") == "token":
            tok = frame["token"]
            buf.append(tok)
            yield f"event: token\ndata: {json.dumps({'token': tok})}\n\n".encode()
        elif frame.get("kind") == "error":
            yield f"event: error\ndata: {json.dumps(frame)}\n\n".encode()
            return

    final = "".join(buf)
    if final:
        async with AsyncSession(engine, expire_on_commit=False) as s:
            await chat_service.append_message(
                s, session_id=session_id, role="assistant", content=final
            )

    yield f"event: done\ndata: {json.dumps({'status': 'completed'})}\n\n".encode()


@router.get("/sessions/{session_id}/stream")
async def stream_session(
    session_id: UUID, user: UserDep, session: SessionDep
):
    """SSE stream of assistant tokens. v0.2 returns a stub frame."""
    s = await chat_service.get_session(
        session, session_id=session_id, user_id=user.id
    )
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session_not_found")
    return StreamingResponse(
        _chat_stream(session_id, user.id),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
