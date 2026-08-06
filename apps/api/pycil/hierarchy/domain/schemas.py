"""Hierarchy DTOs — node CRUD + folder stats."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from pycil.hierarchy.domain.vocabulary import NodeType, Visibility


class NodeCreate(BaseModel):
    type: NodeType
    name: str = Field(min_length=1, max_length=200)
    parent_node_id: UUID | None = Field(default=None, alias="parentNodeId")
    # Required only for REFERENCE nodes — the DECK being referenced.
    target_node_id: UUID | None = Field(default=None, alias="targetNodeId")
    description: str | None = None
    visibility: Visibility = Visibility.PRIVATE
    confirm_subtree_publication: bool = Field(
        default=False, alias="confirmSubtreePublication"
    )

    model_config = {"populate_by_name": True}


class NodeAncestorRead(BaseModel):
    """One breadcrumb hop. Name and type only — enough to render and link."""

    id: UUID
    name: str
    type: NodeType


class NodeRead(BaseModel):
    id: UUID
    type: NodeType
    name: str
    description: str | None = None
    parent_node_id: UUID | None = Field(default=None, serialization_alias="parentNodeId")
    target_node_id: UUID | None = Field(default=None, serialization_alias="targetNodeId")
    visibility: Visibility
    created_at: datetime | None = Field(default=None, serialization_alias="createdAt")
    updated_at: datetime | None = Field(default=None, serialization_alias="updatedAt")
    # Root-first breadcrumb ending at this node. Truncated at the first ancestor
    # the caller cannot read, so it never leaks a private folder's name.
    #
    # Populated by `get_node` ONLY. This is a deliberate, tested asymmetry across
    # the six producers of this DTO, because both fields are optional and would
    # otherwise be silently absent:
    #   get_node                  -> path + item_count populated
    #   list_nodes                -> item_count for DECK rows; path omitted, since
    #                                one walk per row is the N+1 this rebuild removes
    #                                and the caller already knows the parent context
    #   create / update / move /  -> both omitted. A structural mutation invalidates
    #   set_visibility               the caller's node and list queries anyway, so the
    #                                client refetches rather than trusting a response
    #                                that cannot carry sibling or ordering changes.
    path: list[NodeAncestorRead] | None = None
    # Senses held directly by this deck. None for FOLDER and REFERENCE rows, and on
    # the mutation responses above.
    item_count: int | None = Field(default=None, serialization_alias="itemCount")
    model_config = {"from_attributes": True}


class NodeMove(BaseModel):
    parent_node_id: UUID | None = Field(default=None, alias="parentNodeId")

    model_config = {"populate_by_name": True}


class NodeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)


class NodePageRead(BaseModel):
    items: list[NodeRead]
    next_cursor: str | None = Field(default=None, serialization_alias="nextCursor")


class NodeVisibilityUpdate(BaseModel):
    visibility: Visibility
    confirm_subtree_publication: bool = Field(
        default=False, alias="confirmSubtreePublication"
    )

    model_config = {"populate_by_name": True}


class FolderStatsRead(BaseModel):
    total: int
    learned: int
    mastered: int
    avg_mastery: float = Field(serialization_alias="avgMastery")


class WeakSenseRead(BaseModel):
    """A weakest-sense row. Carries enough to render without a second request:
    the previous shape was ``{senseId, mastery}``, which is a progress bar with no
    label."""

    sense_id: int = Field(serialization_alias="senseId")
    mastery: int
    word: str | None = None
    definition: str | None = None
    pos: str | None = None
    cefr_level: str | None = Field(default=None, serialization_alias="cefrLevel")


class FolderItemRead(BaseModel):
    sense_id: int = Field(serialization_alias="senseId")
    definition: str
    tier: str
    cefr_level: str | None = Field(default=None, serialization_alias="cefrLevel")


class HistoryBucketRead(BaseModel):
    bucket: str
    reviewed: int
    avg_mastery: float = Field(serialization_alias="avgMastery")
