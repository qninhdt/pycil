"""Process-owned singleflight for Word generation."""

import asyncio
from collections.abc import Iterable
from typing import Protocol
from uuid import UUID, uuid7

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.app.config import ProductConfig
from pycil.app.http import Problem
from pycil.infrastructure.observability import bound_contextvars, get_logger
from pycil.vocabulary.cache import ContentCache
from pycil.vocabulary.enums import GenerationStage, JobState
from pycil.vocabulary.errors import InvalidHandleError, InvalidResourceError
from pycil.vocabulary.generation.pipeline import generate_word
from pycil.vocabulary.references.reference import fetch_reference
from pycil.vocabulary.schemas import SearchResult
from pycil.vocabulary.text import match_key, validate_lemma
from pycil.vocabulary.types import GenerationTaskState

logger = get_logger(__name__)


class SearchProtocol(Protocol):
    async def search(
        self, query: str, include_reference: bool = False, *, limit: int = 30
    ) -> SearchResult: ...
    async def update(self, word_id: int) -> None: ...


class LLMProtocol(Protocol):
    async def complete[T: BaseModel](self, instruction: str, data: str, schema: type[T]) -> T: ...


class Generations:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        search: SearchProtocol,
        structured_llm: LLMProtocol,
        cache: ContentCache,
        config: ProductConfig,
    ) -> None:
        self.sessions = sessions
        self.search = search
        self.structured_llm = structured_llm
        self.cache = cache
        self.config = config
        self.flights: dict[str, tuple[UUID, asyncio.Task[None]]] = {}
        self.results: dict[UUID, GenerationTaskState] = {}
        self.slots: asyncio.Semaphore = asyncio.Semaphore(128)
        self.closed: bool = False

    async def submit(self, target: str, *, reference_id: str | None = None) -> GenerationTaskState:
        if self.closed:
            raise Problem(503, "generation_unavailable")
        try:
            target = validate_lemma(target)
            if reference_id is not None:
                await fetch_reference(self.sessions, reference_id)
        except InvalidHandleError, InvalidResourceError, ValueError:
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
            return self.results[flight[0]].copy()
        identifier = uuid7()
        result: GenerationTaskState = {
            "task_id": identifier,
            "status": JobState.RUNNING,
            "word_id": None,
            "stage": GenerationStage.WORD,
            "error": None,
            "status_url": f"/v1/word-tasks/{identifier}",
        }
        # shortcut: status lives until restart; bound completed results if volume requires it.
        self.results[identifier] = result
        task = asyncio.create_task(self._run(key, reference_id, target, result))
        self.flights[key] = (identifier, task)
        logger.info(
            "word_generation_started",
            task_id=str(result["task_id"]),
            target=target,
            key=key,
            stage=result["stage"],
        )
        return result.copy()

    def status(self, identifier: UUID) -> GenerationTaskState:
        if identifier not in self.results:
            raise Problem(404, "generation_not_found")
        return self.results[identifier].copy()

    async def wait(self, identifiers: Iterable[UUID]) -> None:
        """One bounded wait for a batch; generation remains process-owned on disconnect."""
        id_set = set(identifiers)
        pending = {task for identifier, task in self.flights.values() if identifier in id_set}
        if pending:
            await asyncio.wait(pending, timeout=min(30, self.config.generation.timeout_seconds))

    async def _run(
        self,
        key: str,
        reference_id: str | None,
        target: str,
        result: GenerationTaskState,
    ) -> None:
        try:
            with bound_contextvars(task_id=str(result["task_id"])):
                async with self.slots, asyncio.timeout(self.config.generation.timeout_seconds):
                    word = await generate_word(
                        self.sessions,
                        self.search,
                        self.structured_llm,
                        self.cache,
                        target,
                        reference_id=reference_id,
                        example_count=self.config.generation.examples_per_sense,
                    )
                    if not word.senses:
                        raise InvalidResourceError("generated Word has no Senses")
                    result["word_id"] = word.id
                    result["status"] = JobState.SUCCEEDED
                    result["stage"] = GenerationStage.READY
                    result["error"] = None
                    logger.info(
                        "word_generation_completed",
                        task_id=str(result["task_id"]),
                        word_id=word.id,
                        target=target,
                        sense_count=len(word.senses),
                        stage=result["stage"],
                    )
        except asyncio.CancelledError:
            logger.warning(
                "word_generation_cancelled",
                task_id=str(result["task_id"]),
                target=target,
            )
            result["status"] = JobState.FAILED
            result["error"] = "generation_interrupted"
            raise
        except TimeoutError:
            logger.warning(
                "word_generation_timed_out",
                task_id=str(result["task_id"]),
                target=target,
            )
            result["status"] = JobState.FAILED
            result["error"] = "generation_timeout"
        except Exception as error:
            logger.error(
                "word_generation_failed",
                error_type=type(error).__name__,
                provider_status_code=getattr(error, "status_code", None),
                provider_error_code=getattr(error, "code", None),
                provider_error_type=getattr(error, "type", None),
                provider_request_id=getattr(error, "request_id", None),
                task_id=str(result["task_id"]),
                target=target,
                key=key,
            )
            result["status"] = JobState.FAILED
            result["error"] = "generation_failed"
        finally:
            self.flights.pop(key, None)

    async def close(self) -> None:
        self.closed = True
        tasks = [task for _, task in self.flights.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.flights.clear()
        self.results.clear()
