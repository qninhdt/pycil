"""Pydantic schemas for nodes (folders + decks)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    FOLDER = "FOLDER"
    DECK = "DECK"


class NodeCreate(BaseModel):
    type: NodeType
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    parent_node_id: UUID | None = None


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
    visibility: Literal["PRIVATE", "PUBLIC"] = "PRIVATE"
    definition_count: int = 0
    is_starred: bool = False
    is_pinned: bool = False
    created_at: datetime
    updated_at: datetime
    breadcrumb: list[BreadcrumbEntry] = Field(default_factory=list)
