"""Hierarchy ORM models: nodes (adjacency list) + attributes + user pins.

A single ``nodes`` table models FOLDER, DECK, and REFERENCE via ``type``.
``parent_node_id`` is the adjacency-list edge; ``target_node_id`` is set only on
REFERENCE nodes (a reusable pointer to another node). No cross-DB refs here —
learnable content is referenced by opaque ``sense_id`` in the content domain.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel

TZDateTime = DateTime(timezone=True)


class NodeType(str, Enum):
    FOLDER = "FOLDER"
    DECK = "DECK"
    REFERENCE = "REFERENCE"


class Visibility(str, Enum):
    PRIVATE = "PRIVATE"
    PUBLIC = "PUBLIC"


class Node(SQLModel, table=True):
    __tablename__ = "nodes"
    __table_args__ = (
        CheckConstraint(
            "(type = 'REFERENCE' AND target_node_id IS NOT NULL) "
            "OR (type <> 'REFERENCE' AND target_node_id IS NULL)",
            name="ck_nodes_reference_target_shape",
        ),
    )

    id: UUID | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
        primary_key=True,
    )
    author_id: UUID = Field(foreign_key="users.id", index=True)
    type: NodeType
    parent_node_id: UUID | None = Field(default=None, foreign_key="nodes.id", index=True)
    # Set only on REFERENCE nodes — points at the node being referenced.
    target_node_id: UUID | None = Field(default=None, foreign_key="nodes.id")
    # Incremented in the same transaction as every structural mutation. Redis
    # keys include this value, so a stale fill can never mask newer structure.
    structural_generation: int = Field(default=0, nullable=False)
    name: str
    description: str | None = None
    visibility: Visibility = Field(default=Visibility.PRIVATE)
    sense_count: int = Field(default=0)
    like_count: int = Field(default=0)
    fork_count: int = Field(default=0)
    created_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
    updated_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
    deleted_at: datetime | None = Field(default=None, sa_type=TZDateTime)


class FolderAttributes(SQLModel, table=True):
    __tablename__ = "folder_attributes"

    node_id: UUID = Field(foreign_key="nodes.id", primary_key=True)
    subfolder_count: int = Field(default=0)


class DeckAttributes(SQLModel, table=True):
    __tablename__ = "deck_attributes"

    node_id: UUID = Field(foreign_key="nodes.id", primary_key=True)
    settings: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )


class UserNode(SQLModel, table=True):
    __tablename__ = "user_nodes"

    user_id: UUID = Field(foreign_key="users.id", primary_key=True)
    node_id: UUID = Field(foreign_key="nodes.id", primary_key=True)
    is_starred: bool = Field(default=False)
    is_pinned: bool = Field(default=False)
    created_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
    updated_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
