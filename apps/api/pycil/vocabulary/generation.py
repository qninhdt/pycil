"""Shared selected-entry requests and finite, resumable neutral-bank filling."""

from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import uuid7

from lexi_ai import QuestionType
from lexi_ai.errors import InvalidHandleError, InvalidResourceError, WordCollisionError
from lexi_ai.inference.retry import retryable
from lexi_ai.references.cambridge import decode_available_id
from lexi_ai.text import validate_lemma
from sqlalchemy import and_, case, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from pycil.http import Problem
from pycil.vocabulary.models import GenerationStatus as Status
from pycil.vocabulary.models import WordGeneration as Request


def projection(row):
    return {
        "generation_id": row.id,
        "status": row.status,
        "word_id": row.word_id,
        "stage": row.stage,
        "error": row.error,
        "status_url": f"/v1/word-generations/{row.id}",
    }


async def coverage(lexicon, sense_ids, config):
    counts = Counter()
    size = config.learning.limits.candidate_read_batch_size
    for start in range(0, len(sense_ids), size):
        counts.update(
            await lexicon.count_questions_for_senses(
                sense_ids[start : start + size], list(QuestionType)
            )
        )
    return counts


async def submit(sessions, lexicon, data, config):
    try:
        identifier = decode_available_id(data.available_id)
        validate_lemma(data.target)
        selected = await lexicon.cambridge.fetch_by_id(identifier)
        if selected is None or not selected.senses:
            raise InvalidHandleError("selection missing")
    except InvalidHandleError, ValueError:
        raise Problem(422, "invalid_generation_selection") from None
    now = datetime.now(UTC)
    async with sessions() as session, session.begin():
        await session.execute(
            insert(Request)
            .values(
                id=uuid7(),
                available_id=data.available_id,
                target=data.target,
                status=Status.QUEUED,
                attempts=0,
                next_attempt_at=now,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=[Request.available_id, Request.target])
        )
        row = await session.scalar(
            select(Request)
            .where(Request.available_id == data.available_id, Request.target == data.target)
            .with_for_update()
        )
        if row.status is Status.FAILED:
            row.status, row.attempts, row.error = Status.QUEUED, 0, None
            row.next_attempt_at = row.updated_at = now
        return projection(row)


async def recover(sessions, config):
    exhausted = Request.attempts >= config.generation.worker.max_attempts
    now = datetime.now(UTC)
    async with sessions() as session, session.begin():
        # Called only by the exclusive worker owner, before polling. Policy
        # changes also retire previously queued jobs that exhausted the new cap.
        await session.execute(
            update(Request)
            .where(
                or_(
                    Request.status == Status.RUNNING,
                    and_(Request.status == Status.QUEUED, exhausted),
                )
            )
            .values(
                status=case((exhausted, Status.FAILED), else_=Status.QUEUED),
                error=case((exhausted, "attempts_exhausted"), else_=None),
                next_attempt_at=now,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )


async def claim(sessions, config):
    async with sessions() as session, session.begin():
        row = await session.scalar(
            select(Request)
            .where(
                Request.status == Status.QUEUED,
                Request.next_attempt_at <= datetime.now(UTC),
                Request.attempts < config.generation.worker.max_attempts,
            )
            .order_by(Request.next_attempt_at, Request.created_at, Request.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is None:
            return None
        row.status, row.stage = Status.RUNNING, "WORD"
        row.attempts += 1
        row.updated_at = datetime.now(UTC)
        await session.flush()
        return row


async def record(sessions, identifier, **values):
    async with sessions() as session, session.begin():
        await session.execute(
            update(Request)
            .where(Request.id == identifier)
            .values(updated_at=datetime.now(UTC), **values)
        )


async def execute(sessions, lexicon, row, config, ensure_owner):
    import asyncio

    word = None
    try:
        async with asyncio.timeout(config.generation.worker.attempt_timeout_seconds):
            word = await lexicon.generate(
                row.available_id,
                target=row.target,
                example_count=config.generation.examples_per_sense,
            )
            if word is None or not word.senses:
                raise InvalidResourceError("generated Word has no Senses")
            await ensure_owner()
            await record(sessions, row.id, word_id=word.id, stage="QUESTION_POOLS")
            ids = [sense.id for sense in word.senses]
            counts = await coverage(lexicon, ids, config)

            async def fill_pool(sense_id, kind):
                try:
                    await lexicon.generate_questions(
                        sense_id,
                        kind,
                        config.generation.questions_per_type,
                        distractor_count=config.generation.distractor_count,
                    )
                except Exception as error:
                    # Native inference already exhausted its bounded retry budget.
                    if not retryable(error):
                        raise

            await ensure_owner()
            tasks = [
                asyncio.create_task(fill_pool(sense_id, kind))
                for sense_id in ids
                for kind in QuestionType
                if not counts[sense_id, kind]
            ]
            try:
                await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            counts = await coverage(lexicon, ids, config)
            partial = any(not counts[s, k] for s in ids for k in QuestionType)
            await ensure_owner()
            await record(
                sessions,
                row.id,
                status=Status.SUCCEEDED,
                stage="PARTIAL" if partial else "READY",
                error="question_pools_incomplete" if partial else None,
            )
    except asyncio.CancelledError:
        raise  # RUNNING is intentionally recovered by the next lock-owning process.
    except Exception as error:
        await ensure_owner()
        if isinstance(error, TimeoutError) and word is not None:
            await record(
                sessions,
                row.id,
                word_id=word.id,
                status=Status.SUCCEEDED,
                stage="PARTIAL",
                error="question_pools_incomplete",
            )
            return
        terminal = isinstance(
            error, (InvalidHandleError, InvalidResourceError, WordCollisionError, ValueError)
        )
        failed = (
            terminal
            or not (retryable(error) or isinstance(error, TimeoutError))
            or row.attempts >= config.generation.worker.max_attempts
        )
        await record(
            sessions,
            row.id,
            status=Status.FAILED if failed else Status.QUEUED,
            error="invalid_selection" if terminal else "generation_failed",
            next_attempt_at=datetime.now(UTC)
            + timedelta(seconds=config.generation.worker.retry_delay_seconds),
        )
