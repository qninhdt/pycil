"""Hierarchy DTOs — node CRUD + folder stats."""

from uuid import UUID

from pydantic import BaseModel, Field

from pycil.hierarchy.models import NodeType, Visibility


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


class NodeRead(BaseModel):
    id: UUID
    type: NodeType
    name: str
    parent_node_id: UUID | None = Field(default=None, serialization_alias="parentNodeId")
    target_node_id: UUID | None = Field(default=None, serialization_alias="targetNodeId")
    visibility: Visibility
    sense_count: int = Field(serialization_alias="senseCount")

    model_config = {"from_attributes": True}


class NodeMove(BaseModel):
    parent_node_id: UUID | None = Field(default=None, alias="parentNodeId")

    model_config = {"populate_by_name": True}


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
    sense_id: int = Field(serialization_alias="senseId")
    mastery: int


class FolderItemRead(BaseModel):
    sense_id: int = Field(serialization_alias="senseId")
    definition: str
    tier: str
    cefr_level: str | None = Field(default=None, serialization_alias="cefrLevel")


class HistoryBucketRead(BaseModel):
    bucket: str
    reviewed: int
    avg_mastery: float = Field(serialization_alias="avgMastery")
