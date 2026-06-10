"""SSE job-stream service coverage.

Pins `stream_job` invariants:
- 404 for missing job AND for a job the user does not own (no oracle).
- Terminal job (completed/failed) emits ONE frame and never subscribes;
  prefers `user_term_jobs.last_event` JSONB, falls back to the job dict.
- Non-term / non-grade job (translate/tts) emits one frame + closes.
- Live term-generation stream subscribes `results:{term_id}`, relays a
  published `completed` frame, then closes.
- Live grade_answer stream subscribes `results:job_{id}`.
- Malformed (non-JSON) channel payload is wrapped as `{"raw": ...}`.
- Heartbeat + hard duration cap fire (constants monkeypatched small).
"""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from pycil_core.services import job_stream_service
from tests.factories import make_term


async def _insert_job(
    session,
    *,
    job_type: str,
    status: str,
    payload: dict,
    created_by=None,
    result=None,
    error=None,
):
    row = (
        await session.execute(
            text(
                """
                INSERT INTO jobs (type, status, payload, result, error, events,
                                  created_by_user_id)
                VALUES (:t, :s, CAST(:p AS jsonb), CAST(:r AS jsonb), :e,
                        CAST('[]' AS jsonb), :uid)
                RETURNING id
                """
            ),
            {
                "t": job_type,
                "s": status,
                "p": json.dumps(payload),
                "r": json.dumps(result) if result is not None else None,
                "e": error,
                "uid": str(created_by) if created_by else None,
            },
        )
    ).one()
    await session.commit()
    return row.id


async def _link_user_term_job(session, *, user_id, term_id, job_id, last_event=None):
    await session.execute(
        text(
            """
            INSERT INTO user_term_jobs (user_id, term_id, job_id, last_event)
            VALUES (:u, :t, :j, CAST(:le AS jsonb))
            """
        ),
        {
            "u": str(user_id),
            "t": term_id,
            "j": str(job_id),
            "le": json.dumps(last_event) if last_event is not None else None,
        },
    )
    await session.commit()


def _decode(frame: bytes) -> str:
    return frame.decode() if isinstance(frame, bytes) else frame


# ---------------------------------------------------------------------------
# 404 / ownership.
# ---------------------------------------------------------------------------

async def test_missing_job_raises_404(session, test_user) -> None:
    gen = job_stream_service.stream_job(
        session, user_id=test_user["id"], job_id=uuid4()
    )
    with pytest.raises(HTTPException) as exc:
        await gen.__anext__()
    assert exc.value.status_code == 404
    assert exc.value.detail == "job_not_found"


async def test_other_users_job_raises_404(session, test_user, second_user) -> None:
    """Job owned by another user → 404, no timing oracle."""
    job_id = await _insert_job(
        session,
        job_type="translate",
        status="running",
        payload={},
        created_by=second_user["id"],
    )
    gen = job_stream_service.stream_job(
        session, user_id=test_user["id"], job_id=job_id
    )
    with pytest.raises(HTTPException) as exc:
        await gen.__anext__()
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Terminal jobs: one frame, no subscribe.
# ---------------------------------------------------------------------------

async def test_terminal_completed_prefers_last_event(session, test_user) -> None:
    term_id = await make_term(session, value="stream-term-complete")
    job_id = await _insert_job(
        session,
        job_type="generate_term",
        status="completed",
        payload={"term_id": term_id},
        created_by=test_user["id"],
    )
    last_event = {"status": "completed", "definitions": [{"id": 1}]}
    await _link_user_term_job(
        session,
        user_id=test_user["id"],
        term_id=term_id,
        job_id=job_id,
        last_event=last_event,
    )

    frames = [f async for f in job_stream_service.stream_job(
        session, user_id=test_user["id"], job_id=job_id
    )]
    assert len(frames) == 1
    text_frame = _decode(frames[0])
    assert text_frame.startswith("event: status\n")
    assert '"definitions"' in text_frame


async def test_terminal_failed_falls_back_to_job_dict(session, test_user) -> None:
    """Failed job with no user_term_jobs row → frame carries job dict."""
    job_id = await _insert_job(
        session,
        job_type="generate_term",
        status="failed",
        payload={"term_id": 999},
        created_by=test_user["id"],
        error="llm_timeout",
    )
    frames = [f async for f in job_stream_service.stream_job(
        session, user_id=test_user["id"], job_id=job_id
    )]
    assert len(frames) == 1
    text_frame = _decode(frames[0])
    assert '"status": "failed"' in text_frame
    assert "llm_timeout" in text_frame


# ---------------------------------------------------------------------------
# Non-term / non-grade job: one frame + close, no channel.
# ---------------------------------------------------------------------------

async def test_non_term_job_single_frame_then_close(session, test_user) -> None:
    job_id = await _insert_job(
        session,
        job_type="translate",
        status="running",
        payload={},
        created_by=test_user["id"],
    )
    frames = [f async for f in job_stream_service.stream_job(
        session, user_id=test_user["id"], job_id=job_id
    )]
    assert len(frames) == 1
    assert '"status": "running"' in _decode(frames[0])


# ---------------------------------------------------------------------------
# Live streams (term + grade) via fakeredis pubsub.
# ---------------------------------------------------------------------------

async def _collect_with_publish(gen, fakeredis_client, channel, payloads, delay=0.15):
    """Drive `gen` to completion while publishing `payloads` after subscribe."""
    frames: list = []

    async def consume():
        async for f in gen:
            frames.append(f)

    async def publish():
        await asyncio.sleep(delay)
        for p in payloads:
            await fakeredis_client.publish(
                channel, p if isinstance(p, str) else json.dumps(p)
            )
            await asyncio.sleep(0.02)

    await asyncio.wait_for(asyncio.gather(consume(), publish()), timeout=10)
    return frames


async def test_live_term_stream_relays_completed(
    session, test_user, fakeredis_client
) -> None:
    term_id = await make_term(session, value="stream-live-term")
    job_id = await _insert_job(
        session,
        job_type="generate_term",
        status="running",
        payload={"term_id": term_id},
        created_by=test_user["id"],
    )
    gen = job_stream_service.stream_job(
        session, user_id=test_user["id"], job_id=job_id
    )
    frames = await _collect_with_publish(
        gen,
        fakeredis_client,
        f"results:{term_id}",
        [{"status": "completed", "term_id": term_id}],
    )
    text_frames = [_decode(f) for f in frames]
    # First frame is the initial {id,status}; a later frame carries completed.
    assert any('"status": "running"' in t for t in text_frames)
    assert any('"status": "completed"' in t for t in text_frames)


async def test_live_grade_stream_uses_job_channel(
    session, test_user, fakeredis_client
) -> None:
    """grade_answer job (no term_id) publishes on results:job_{id}."""
    job_id = await _insert_job(
        session,
        job_type="grade_answer",
        status="running",
        payload={},
        created_by=test_user["id"],
    )
    gen = job_stream_service.stream_job(
        session, user_id=test_user["id"], job_id=job_id
    )
    frames = await _collect_with_publish(
        gen,
        fakeredis_client,
        f"results:job_{job_id}",
        [{"status": "failed", "error": "grading_failed"}],
    )
    text_frames = [_decode(f) for f in frames]
    assert any('"status": "failed"' in t for t in text_frames)


async def test_live_stream_wraps_malformed_payload(
    session, test_user, fakeredis_client
) -> None:
    """Non-JSON channel data is wrapped as {"raw": ...} before the close frame."""
    term_id = await make_term(session, value="stream-malformed")
    job_id = await _insert_job(
        session,
        job_type="generate_term",
        status="running",
        payload={"term_id": term_id},
        created_by=test_user["id"],
    )
    gen = job_stream_service.stream_job(
        session, user_id=test_user["id"], job_id=job_id
    )
    frames = await _collect_with_publish(
        gen,
        fakeredis_client,
        f"results:{term_id}",
        ["this-is-not-json", {"status": "completed"}],
    )
    text_frames = [_decode(f) for f in frames]
    assert any('"raw"' in t and "this-is-not-json" in t for t in text_frames)
    assert any('"completed"' in t for t in text_frames)


async def test_live_stream_heartbeat_then_timeout(
    session, test_user, fakeredis_client, monkeypatch
) -> None:
    """No messages → heartbeat frame(s) emitted, then hard-cap timeout frame."""
    monkeypatch.setattr(job_stream_service, "_HEARTBEAT_INTERVAL", 0.05)
    monkeypatch.setattr(job_stream_service, "_MAX_DURATION", 0.3)

    term_id = await make_term(session, value="stream-heartbeat")
    job_id = await _insert_job(
        session,
        job_type="generate_term",
        status="running",
        payload={"term_id": term_id},
        created_by=test_user["id"],
    )
    frames = [f async for f in job_stream_service.stream_job(
        session, user_id=test_user["id"], job_id=job_id
    )]
    text_frames = [_decode(f) for f in frames]
    assert any(": heartbeat" in t for t in text_frames)
    assert any("event: timeout" in t for t in text_frames)
