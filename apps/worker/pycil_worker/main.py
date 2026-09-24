"""Worker startup: resources, job registration and liveness.

One broker, one consumer group, two registered handlers. The resources a job needs
(Redis, the database session factory, the embedded Lexi engine) are built once at
startup and handed to handlers through the broker's state, so a handler never
opens its own connections and a test can substitute them.

The worker registers exactly the handlers named by the shared contract's registry
and fails at import if it does not cover every kind — a missing registration would
otherwise leave a queued job unhandled forever, which looks to a learner like a
job stuck in `queued`.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import suppress
from typing import Any
from uuid import uuid4

import pycil.db.models  # noqa: F401 - register ORM metadata before any job writes
from lexi_ai import Lexicon
from pycil.config import settings
from pycil.ports.lexi_embedded import create_lexicon_reader
from pycil.queue.contracts import (
    JOB_NAME_FOR_KIND,
    PAYLOAD_VERSION,
    WORKER_HEARTBEAT_KEY,
    WORKER_HEARTBEAT_TTL_SECONDS,
)
from pycil.queue.receipts import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_RUNNING,
    update_job_status,
)
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from taskiq import TaskiqEvents

from pycil_worker.broker import broker
from pycil_worker.jobs.generate_question import prepare_questions
from pycil_worker.jobs.generate_word import generate_word
from pycil_worker.lexi_library import create_lexicon_worker_engine

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 10.0


async def _build_resources() -> dict[str, Any]:
    """Construct the long-lived resources every job shares."""
    lexicon = Lexicon.from_settings()
    redis = Redis.from_url(settings.redis_url)
    engine = create_async_engine(settings.db_url, pool_pre_ping=True)
    await redis.ping()
    return {
        "worker_id": str(uuid4()),
        "redis": redis,
        "engine": engine,
        "session_factory": async_sessionmaker(engine, expire_on_commit=False),
        "lexicon": lexicon,
        "lexi_reader": create_lexicon_reader(lexicon),
        "lexi_engine": create_lexicon_worker_engine(lexicon),
    }


async def _close_resources(resources: dict[str, Any]) -> None:
    if lexicon := resources.get("lexicon"):
        await lexicon.close()
    if engine := resources.get("engine"):
        await engine.dispose()
    if redis := resources.get("redis"):
        await redis.aclose()


async def _heartbeat_loop(resources: dict[str, Any]) -> None:
    """Refresh the liveness key the API readiness probe reads.

    A worker that dies stops refreshing and the key expires, so readiness fails
    rather than reporting healthy against a broker nothing is consuming.
    """
    redis = resources["redis"]
    while True:
        try:
            await redis.setex(
                WORKER_HEARTBEAT_KEY,
                WORKER_HEARTBEAT_TTL_SECONDS,
                resources["worker_id"],
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("worker_heartbeat_failed")
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)


#: Which handler serves each kind. The keys must equal the shared contract's
#: registry; the assertion below turns a mismatch into a startup failure rather
#: than a job that sits queued forever.
_HANDLERS = {
    "word": generate_word,
    "question_supply": prepare_questions,
}


def _register_jobs() -> None:
    """Register one handler per contract kind, refusing to start on a gap."""
    if set(_HANDLERS) != set(JOB_NAME_FOR_KIND):
        missing = sorted(set(JOB_NAME_FOR_KIND) - set(_HANDLERS))
        extra = sorted(set(_HANDLERS) - set(JOB_NAME_FOR_KIND))
        raise RuntimeError(f"worker_handler_registry_mismatch missing={missing} extra={extra}")

    for kind, handler in _HANDLERS.items():
        broker.register_task(
            _make_receipted_handler(kind, handler),
            task_name=JOB_NAME_FOR_KIND[kind],
        )


def _make_receipted_handler(kind: str, handler):
    """Wrap one job so it records its own receipt transitions.

    The receipt is written to `running` before the effect and to a terminal state
    after, so a polling client sees progress rather than one jump. A handler
    failure is recorded with a bounded error code — never the raw exception text,
    which can carry provider URLs or prompt fragments.
    """

    async def run(job_id: str, payload: dict, payload_version: int) -> dict:
        if payload_version != PAYLOAD_VERSION:
            raise RuntimeError(f"unsupported_payload_version: {payload_version}")
        resources = _resources()
        redis = resources["redis"]
        await update_job_status(redis, job_id, STATUS_RUNNING)
        try:
            result = await handler(resources, payload)
        except Exception as exc:
            logger.exception("job_failed", extra={"kind": kind})
            await update_job_status(redis, job_id, STATUS_FAILED, error=_error_code(exc))
            raise
        await update_job_status(redis, job_id, STATUS_DONE, result=result)
        return result

    run.__name__ = f"run_{kind}"
    return run


def _error_code(exc: Exception) -> str:
    """A stable, non-sensitive error code for the receipt.

    The exception's own message is deliberately not used: a provider error can
    embed the request URL, a key fragment or part of the prompt.
    """
    text = str(exc)
    if text == "question_supply_unavailable":
        return text
    return "job_failed"


def _resources() -> dict[str, Any]:
    state = broker.state
    if not hasattr(state, "worker"):
        raise RuntimeError("worker_resources_not_initialized")
    return state.worker


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _startup(state) -> None:
    resources = await _build_resources()
    state.worker = resources
    resources["heartbeat_task"] = asyncio.create_task(_heartbeat_loop(resources))
    logger.info("worker_started", extra={"worker_id": resources["worker_id"]})


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def _shutdown(state) -> None:
    resources = getattr(state, "worker", None)
    if not resources:
        return
    if pulse := resources.get("heartbeat_task"):
        pulse.cancel()
        with suppress(asyncio.CancelledError):
            await pulse
    await _close_resources(resources)


_register_jobs()


def main() -> None:
    """Run the worker until a termination signal arrives."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    stop = asyncio.Event()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    try:
        loop.run_until_complete(broker.startup())
        loop.run_until_complete(stop.wait())
    finally:
        loop.run_until_complete(broker.shutdown())
        loop.close()


if __name__ == "__main__":
    main()
