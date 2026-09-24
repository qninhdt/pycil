"""Immutable dependencies injected into LangChain tools at invocation time."""

from dataclasses import dataclass, field
from uuid import UUID

from pycil.assistant.domain.usage import TurnUsage


@dataclass(frozen=True)
class AssistantContext:
    """The actor a run belongs to, the model it selected, and its metering.

    Just the internal UUID for identity: every tool re-checks ownership against
    it, and Clerk owns session validity, so there is no credential state to carry
    along. The model fields hold a selection the router already validated against
    the catalog, so the graph never re-decides what a learner is allowed to run.

    ``usage`` is the one mutable member. It is per-run rather than per-graph
    because the graph is built once per process and serves every learner: a
    module-level accumulator would mix one turn's tokens into another's bill.
    The middleware writes to it as calls complete and the run service reads it
    once, at settlement.
    """

    user_id: UUID
    model_id: str | None = None
    reasoning_effort: str | None = None
    usage: TurnUsage = field(default_factory=TurnUsage)
