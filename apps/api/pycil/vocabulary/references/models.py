"""Immutable reference identity and the fields consumed by lexical generation/search."""

from sqlalchemy import CheckConstraint, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pycil.infrastructure.database import Base, enum_column
from pycil.vocabulary.enums import EntryType


class ReferenceSense(Base):
    __tablename__ = "reference_senses"
    __table_args__ = (
        CheckConstraint("length(btrim(definition)) > 0", name="definition_present"),
        CheckConstraint("entry_order >= 0 AND sense_order >= 0", name="source_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    word_id: Mapped[int] = mapped_column(
        ForeignKey("reference_words.id", ondelete="RESTRICT"), index=True
    )
    definition: Mapped[str] = mapped_column(Text)
    pos: Mapped[str | None] = mapped_column(Text)
    headword: Mapped[str | None] = mapped_column(Text)
    phrase_title: Mapped[str | None] = mapped_column(Text)
    ipa_uk: Mapped[str | None] = mapped_column(Text)
    ipa_us: Mapped[str | None] = mapped_column(Text)
    entry_order: Mapped[int] = mapped_column()
    sense_order: Mapped[int] = mapped_column()


class ReferenceWord(Base):
    __tablename__ = "reference_words"
    __table_args__ = (
        CheckConstraint("length(btrim(lemma)) > 0", name="lemma_present"),
        CheckConstraint("length(btrim(display_form)) > 0", name="display_present"),
        CheckConstraint(
            "jsonb_typeof(alternatives) = 'array' AND jsonb_typeof(inflections) = 'array'",
            name="search_surfaces",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    lemma: Mapped[str] = mapped_column(Text)
    display_form: Mapped[str] = mapped_column(Text)
    entry_type: Mapped[EntryType] = mapped_column(enum_column(EntryType))
    alternatives: Mapped[list[list[str]]] = mapped_column(JSONB)
    inflections: Mapped[list[str]] = mapped_column(JSONB)
