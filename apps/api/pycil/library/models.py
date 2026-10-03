from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid7

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from pycil.database import Base, enum_column


class NodeType(StrEnum):
    FOLDER = "FOLDER"
    DECK = "DECK"
    REFERENCE = "REFERENCE"


class Visibility(StrEnum):
    PRIVATE = "PRIVATE"
    PUBLIC = "PUBLIC"


class CollectionNode(Base):
    __tablename__ = "collection_nodes"
    __table_args__ = (
        CheckConstraint("parent_id IS NULL OR parent_id != id", name="not_own_parent"),
        CheckConstraint("reference_id IS NULL OR reference_id != id", name="not_own_reference"),
        CheckConstraint(
            "(type = 'REFERENCE') = (reference_id IS NOT NULL)", name="reference_shape"
        ),
        Index("ix_nodes_owner_parent_order", "owner_id", "parent_id", "created_at", "id"),
        Index(
            "ix_nodes_public_root_order",
            "created_at",
            "id",
            postgresql_where=text(
                "parent_id IS NULL AND deleted_at IS NULL AND visibility = 'PUBLIC'"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[NodeType] = mapped_column(enum_column(NodeType))
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("collection_nodes.id", ondelete="CASCADE"), index=True
    )
    reference_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("collection_nodes.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[Visibility] = mapped_column(
        enum_column(Visibility), default=Visibility.PRIVATE
    )
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
        ForeignKey("collection_nodes.id", ondelete="CASCADE"), primary_key=True
    )
    sense_id: Mapped[int] = mapped_column(
        ForeignKey("lexi.senses.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
