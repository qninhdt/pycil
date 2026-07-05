"""Content membership models.

pycil stores ONLY deck membership as opaque ``sense_id`` refs. Dictionary
content (words/senses/questions) lives in lexi-ai's SEPARATE database — never
FK'd, never JOINed across. ``sense_id`` is a plain bigint pointer.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, UniqueConstraint, text
from sqlmodel import Column, Field, SQLModel

TZDateTime = DateTime(timezone=True)


class DeckSense(SQLModel, table=True):
    __tablename__ = "deck_senses"
    __table_args__ = (UniqueConstraint("node_id", "sense_id", name="uq_deck_senses_node_sense"),)

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    node_id: UUID = Field(foreign_key="nodes.id", index=True)
    # Opaque ref into lexi-ai's DB. No FK — cross-DB boundary.
    sense_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    position: int = Field(default=0)
    created_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
