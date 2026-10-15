"""Typed data structures and dictionaries for the library domain."""

from datetime import datetime
from typing import Literal, TypedDict
from uuid import UUID

from pycil.library.models import NodeRole, NodeSpace, NodeType
from pycil.study.enums import LearningState
from pycil.study.types import SummaryDict


class SourceDeckDict(TypedDict):
    id: UUID
    name: str
    owner_id: UUID | None
    space: NodeSpace
    editable: bool


class SenseSourcesSummary(TypedDict):
    decks: list[SourceDeckDict]
    count: int


class LearningPreviewDict(TypedDict):
    state: Literal[LearningState.NEW, LearningState.DUE, LearningState.NOT_YET_DUE]
    due_at: datetime | None
    elo: float | None
    level: int | None
    last_reviewed_at: datetime | None


class BreadcrumbDict(TypedDict):
    id: UUID
    name: str


class NodeViewDict(TypedDict):
    id: UUID
    owner_id: UUID
    type: NodeType
    parent_id: UUID | None
    reference_id: UUID | None
    name: str
    description: str | None
    role: NodeRole
    space: NodeSpace
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    summary: SummaryDict | None


class SavedDeckDict(NodeViewDict):
    sense_ids: list[int]
    retained_reference_id: UUID | None


class NodeDetailsDict(NodeViewDict):
    breadcrumbs: list[BreadcrumbDict]
    reference_available: bool | None


class NodePageDict(TypedDict):
    nodes: list[dict[str, object]]
    next_cursor: str | None


class SourcesPageDict(TypedDict):
    decks: list[SourceDeckDict]
    next_cursor: str | None
