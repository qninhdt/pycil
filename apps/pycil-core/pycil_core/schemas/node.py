"""Pydantic schemas for nodes (folders + decks)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class NodeType(str, Enum):
    FOLDER = "FOLDER"
    DECK = "DECK"
    SHORTCUT = "SHORTCUT"


class NodeCreate(BaseModel):
    type: NodeType
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    parent_node_id: UUID | None = None
    # Only meaningful for SHORTCUT: the node this shortcut points at. The service
    # validates the target exists and is owned by the caller.
    target_node_id: UUID | None = None

    @model_validator(mode="after")
    def _shortcut_requires_target(self) -> "NodeCreate":
        if self.type == NodeType.SHORTCUT and self.target_node_id is None:
            raise ValueError("target_node_id is required for SHORTCUT")
        if self.type != NodeType.SHORTCUT and self.target_node_id is not None:
            raise ValueError("target_node_id is only valid for SHORTCUT")
        return self


class NodeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)


class BreadcrumbEntry(BaseModel):
    id: UUID
    name: str
    type: NodeType


class NodeRead(BaseModel):
    id: UUID
    type: NodeType
    name: str
    description: str | None
    parent_node_id: UUID | None
    # Set only for SHORTCUT nodes — the node this shortcut navigates to.
    target_node_id: UUID | None = None
    visibility: Literal["PRIVATE", "PUBLIC"] = "PRIVATE"
    definition_count: int = 0
    is_starred: bool = False
    is_pinned: bool = False
    created_at: datetime
    updated_at: datetime
    breadcrumb: list[BreadcrumbEntry] = Field(default_factory=list)
