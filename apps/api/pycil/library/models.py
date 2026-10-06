from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid7

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from pycil.database import Base, enum_column


class NodeType(StrEnum):
    FOLDER = "FOLDER"
    DECK = "DECK"
    REFERENCE = "REFERENCE"


class NodeRole(StrEnum):
    NORMAL = "NORMAL"
    LIBRARY_ROOT = "LIBRARY_ROOT"
    PERSONAL_ROOT = "PERSONAL_ROOT"
    PUBLISHED_ROOT = "PUBLISHED_ROOT"


class NodeSpace(StrEnum):
    LIBRARY = "LIBRARY"
    PERSONAL = "PERSONAL"
    PUBLISHED = "PUBLISHED"


class Node(Base):
    __tablename__ = "nodes"
    __table_args__ = (
        Index("ix_nodes_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_nodes_published_owner_order",
            "owner_id",
            "created_at",
            "id",
            postgresql_where=text("deleted_at IS NULL AND space = 'PUBLISHED' AND role = 'NORMAL'"),
        ),
        CheckConstraint("parent_id IS NULL OR parent_id != id", name="not_own_parent"),
        CheckConstraint("reference_id IS NULL OR reference_id != id", name="not_own_reference"),
        CheckConstraint(
            "(type = 'REFERENCE') = (reference_id IS NOT NULL)", name="reference_shape"
        ),
        CheckConstraint("(role = 'LIBRARY_ROOT') = (parent_id IS NULL)", name="root_shape"),
        CheckConstraint("role = 'NORMAL' OR type = 'FOLDER'", name="system_folder"),
        UniqueConstraint("owner_id", "id"),
        ForeignKeyConstraint(
            ["owner_id", "parent_id"], ["nodes.owner_id", "nodes.id"], ondelete="CASCADE"
        ),
        Index(
            "uq_nodes_owner_role",
            "owner_id",
            "role",
            unique=True,
            postgresql_where=text("role != 'NORMAL'"),
        ),
        Index(
            "ix_nodes_owner_parent_order",
            "owner_id",
            "parent_id",
            "created_at",
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_nodes_published_order",
            "created_at",
            "id",
            postgresql_where=text("deleted_at IS NULL AND space = 'PUBLISHED' AND role = 'NORMAL'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[NodeType] = mapped_column(enum_column(NodeType))
    parent_id: Mapped[UUID | None] = mapped_column(index=True)
    reference_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('simple'::regconfig, coalesce(name, '')), 'A') || "
            "setweight(to_tsvector('simple'::regconfig, coalesce(description, '')), 'B')",
            persisted=True,
        ),
    )
    role: Mapped[NodeRole] = mapped_column(enum_column(NodeRole), default=NodeRole.NORMAL)
    space: Mapped[NodeSpace] = mapped_column(enum_column(NodeSpace))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class DeckSense(Base):
    __tablename__ = "deck_senses"

    deck_id: Mapped[UUID] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True
    )
    sense_id: Mapped[int] = mapped_column(
        ForeignKey("lexi.senses.id", ondelete="RESTRICT"), primary_key=True, index=True
    )


class NodePath(Base):
    """Synchronous physical closure; reference edges never enter this table."""

    __tablename__ = "node_paths"
    __table_args__ = (
        CheckConstraint("depth >= 0", name="nonnegative_depth"),
        CheckConstraint("(ancestor_id = descendant_id) = (depth = 0)", name="self_depth"),
        Index("ix_node_paths_descendant", "descendant_id", "ancestor_id"),
    )

    ancestor_id: Mapped[UUID] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True
    )
    descendant_id: Mapped[UUID] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True
    )
    depth: Mapped[int] = mapped_column()
