"""Process-owned singleflight for Word generation."""

import asyncio
from uuid import uuid7

from lexi_ai.errors import InvalidHandleError, InvalidResourceError
from lexi_ai.text import match_key, validate_lemma

from pycil.http import Problem
from pycil.logging import get_logger

logger = get_logger(__name__)


class Generations:
    def __init__(self, lexicon, config):
        self.lexicon, self.config = lexicon, config
        self.flights, self.results = {}, {}
        self.slots = asyncio.Semaphore(128)
        self.closed = False

    async def submit(self, target, *, reference_id=None):
        if self.closed:
            raise Problem(503, "generation_unavailable")
        try:
            target = validate_lemma(target)
            if reference_id is not None:
                await self.lexicon.validate_reference(reference_id)
        except InvalidHandleError, ValueError:
            raise Problem(422, "invalid_generation_selection") from None
        if self.closed:
            raise Problem(503, "generation_unavailable")
        key = reference_id if reference_id is not None else "word:" + match_key(target)
        if flight := self.flights.get(key):
            logger.info(
                "word_generation_deduplicated",
                task_id=str(flight[0]),
                target=target,
                key=key,
            )
            return dict(self.results[flight[0]])
        identifier = uuid7()
        result = {
            "task_id": identifier,
            "status": "RUNNING",
            "word_id": None,
            "stage": "WORD",
            "error": None,
            "status_url": f"/v1/word-tasks/{identifier}",
        }
        # shortcut: status lives until restart; bound completed results if volume requires it.
        self.results[identifier] = result
        task = asyncio.create_task(self._run(key, reference_id, target, result))
        self.flights[key] = identifier, task
        logger.info(
            "word_generation_started",
            task_id=str(result["task_id"]),
            target=target,
            key=key,
        )
        return dict(result)

    def status(self, identifier):
        if identifier not in self.results:
            raise Problem(404, "generation_not_found")
        return dict(self.results[identifier])

    async def wait(self, identifiers):
        """One bounded wait for a batch; generation remains process-owned on disconnect."""
        identifiers = set(identifiers)
        pending = {task for identifier, task in self.flights.values() if identifier in identifiers}
        if pending:
            await asyncio.wait(pending, timeout=min(30, self.config.generation.timeout_seconds))

    async def _run(self, key, reference_id, target, result):
        try:
            async with self.slots, asyncio.timeout(self.config.generation.timeout_seconds):
                word = await self.lexicon.generate_word(
                    target,
                    reference_id=reference_id,
                    example_count=self.config.generation.examples_per_sense,
                )
                if word is None or not word.senses:
                    raise InvalidResourceError("generated Word has no Senses")
                result.update(word_id=word.id, status="SUCCEEDED", stage="READY", error=None)
                logger.info(
                    "word_generation_completed",
                    task_id=str(result["task_id"]),
                    word_id=word.id,
                    target=target,
                    sense_count=len(word.senses),
                )
        except asyncio.CancelledError:
            logger.warning(
                "word_generation_cancelled",
                task_id=str(result["task_id"]),
                target=target,
            )
            result.update(status="FAILED", error="generation_interrupted")
            raise
        except TimeoutError:
            logger.warning(
                "word_generation_timed_out",
                task_id=str(result["task_id"]),
                target=target,
            )
            result.update(status="FAILED", error="generation_timeout")
        except Exception:
            logger.exception(
                "word_generation_failed",
                task_id=str(result["task_id"]),
                target=target,
                key=key,
            )
            result.update(status="FAILED", error="generation_failed")
        finally:
            self.flights.pop(key, None)

    async def close(self):
        self.closed = True
        tasks = [task for _, task in self.flights.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.flights.clear()
        self.results.clear()
