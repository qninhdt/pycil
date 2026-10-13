import asyncio
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.infrastructure.observability import get_logger
from pycil.vocabulary.enums import ResolutionState
from pycil.vocabulary.errors import InvalidOutputError
from pycil.vocabulary.relations.decisions import RELATION_RULES, relation_selection_model
from pycil.vocabulary.relations.storage import (
    Candidate,
    ClearableCache,
    PendingLink,
    apply_resolution,
    pending_relations,
)

logger = get_logger(__name__)


class DecisionLLM(Protocol):
    async def decide[T: BaseModel](self, schema: type[T], context: dict[str, object]) -> T: ...


@dataclass(frozen=True)
class Resolution:
    edge_id: int
    state: ResolutionState
    error: str | None = None


async def resolve_relations(
    sessions: async_sessionmaker[AsyncSession],
    decision_llm: DecisionLLM,
    batch_size: int = 20,
    *,
    cache: ClearableCache | None = None,
) -> list[Resolution]:
    pending = await pending_relations(sessions, batch_size)

    async def resolve(link: PendingLink) -> Resolution:
        try:
            if link.source_definition is None or any(
                candidate.definition is None for candidate in link.candidates
            ):
                raise InvalidOutputError("relation has incomplete neutral evidence")
            selected: Candidate | None = None
            if link.candidates:
                candidates: dict[str, Candidate] = {
                    f"candidate_{index}": candidate
                    for index, candidate in enumerate(link.candidates, 1)
                }
                response = await decision_llm.decide(
                    relation_selection_model(link),
                    {
                        "source": {"word": link.source_word, "definition": link.source_definition},
                        "relation": {
                            "type": link.relation_type.value,
                            "rule": RELATION_RULES[link.relation_type],
                        },
                        "target": {"word": link.target_word},
                    },
                )
                choice = response.matched_sense
                if choice != "no_candidate":
                    if choice not in candidates:
                        raise InvalidOutputError("decision selected unavailable relation evidence")
                    selected = candidates[choice]
            applied = await apply_resolution(sessions, link, selected, cache=cache)
            state = (
                ResolutionState.NOOP
                if not applied
                else ResolutionState.RESOLVED
                if selected
                else ResolutionState.UNRESOLVABLE
            )
            logger.info("relation_resolution_completed", edge_id=link.edge_id, outcome=state.value)
            return Resolution(link.edge_id, state)
        except Exception as error:
            category = type(error).__name__
            logger.warning("relation_resolution_failed", edge_id=link.edge_id, error_type=category)
            return Resolution(link.edge_id, ResolutionState.ERROR, category)

    tasks = [asyncio.create_task(resolve(link)) for link in pending]
    try:
        return list(await asyncio.gather(*tasks))
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
