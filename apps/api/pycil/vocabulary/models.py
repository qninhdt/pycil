"""Lexical facts owned by the application metadata."""

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from pycil.infrastructure.database import Base, enum_column
from pycil.vocabulary.enums import (
    CEFRLevel,
    EntryType,
    GenerationState,
    Inflection,
    PartOfSpeech,
    ReferenceSource,
    Register,
    SenseRelationType,
    Tier,
    WordRelationType,
)


class Word(Base):
    __tablename__ = "words"
    __table_args__ = (
        Index(
            "ix_words_match_key_prefix",
            "match_key",
            postgresql_ops={"match_key": "varchar_pattern_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lemma: Mapped[str] = mapped_column(Text)
    match_key: Mapped[str] = mapped_column(String(512), unique=True)
    entry_type: Mapped[EntryType | None] = mapped_column(enum_column(EntryType))
    generation_state: Mapped[GenerationState] = mapped_column(
        enum_column(GenerationState), default=GenerationState.PENDING
    )


class WordAlias(Base):
    __tablename__ = "word_aliases"
    __table_args__ = (
        UniqueConstraint("word_id", "match_key"),
        Index(
            "ix_word_aliases_match_key",
            "match_key",
            postgresql_ops={"match_key": "varchar_pattern_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(Text)
    match_key: Mapped[str] = mapped_column(String(512))


class WordReference(Base):
    __tablename__ = "word_references"

    id: Mapped[int] = mapped_column(primary_key=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("reference_words.id", ondelete="RESTRICT"), unique=True
    )


class Sense(Base):
    __tablename__ = "senses"
    __table_args__ = (Index("ix_senses_word_pos_order", "word_id", "pos", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"), index=True)
    pos: Mapped[PartOfSpeech] = mapped_column(enum_column(PartOfSpeech))
    tier: Mapped[Tier] = mapped_column(enum_column(Tier))
    cefr_level: Mapped[CEFRLevel | None] = mapped_column(enum_column(CEFRLevel))
    register: Mapped[Register | None] = mapped_column(enum_column(Register))
    ipa_uk: Mapped[str | None] = mapped_column(String(80))
    ipa_us: Mapped[str | None] = mapped_column(String(80))


class Definition(Base):
    __tablename__ = "definitions"
    __table_args__ = (
        Index(
            "ux_definitions_neutral",
            "sense_id",
            unique=True,
            postgresql_where=text("theme_id IS NULL"),
        ),
        UniqueConstraint("sense_id", "theme_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sense_id: Mapped[int] = mapped_column(ForeignKey("senses.id", ondelete="CASCADE"))
    theme_id: Mapped[int | None] = mapped_column(
        ForeignKey("themes.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)


class Example(Base):
    __tablename__ = "examples"
    __table_args__ = (Index("ix_examples_scope", "sense_id", "theme_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sense_id: Mapped[int] = mapped_column(ForeignKey("senses.id", ondelete="CASCADE"))
    theme_id: Mapped[int | None] = mapped_column(
        ForeignKey("themes.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)


class SenseForm(Base):
    __tablename__ = "sense_forms"
    __table_args__ = (
        Index(
            "ix_sense_forms_match_key",
            "match_key",
            postgresql_ops={"match_key": "varchar_pattern_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sense_id: Mapped[int] = mapped_column(ForeignKey("senses.id", ondelete="CASCADE"), index=True)
    surface: Mapped[str] = mapped_column(Text)
    inf: Mapped[Inflection] = mapped_column(enum_column(Inflection))
    match_key: Mapped[str] = mapped_column(String(512))
    head_key: Mapped[str] = mapped_column(String(512), index=True)


class SensePattern(Base):
    __tablename__ = "sense_patterns"

    id: Mapped[int] = mapped_column(primary_key=True)
    sense_id: Mapped[int] = mapped_column(ForeignKey("senses.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    head_key: Mapped[str | None] = mapped_column(String(512), index=True)


class Collocation(Base):
    __tablename__ = "collocations"

    id: Mapped[int] = mapped_column(primary_key=True)
    sense_id: Mapped[int] = mapped_column(ForeignKey("senses.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)


class SenseReference(Base):
    __tablename__ = "sense_references"
    __table_args__ = (UniqueConstraint("sense_id", "source", "source_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sense_id: Mapped[int] = mapped_column(ForeignKey("senses.id", ondelete="CASCADE"), index=True)
    source: Mapped[ReferenceSource] = mapped_column(enum_column(ReferenceSource))
    source_ref: Mapped[str] = mapped_column(String(255))


class WordRelation(Base):
    __tablename__ = "word_relations"
    __table_args__ = (UniqueConstraint("from_word_id", "to_word_id", "rel_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    from_word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"))
    to_word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"), index=True)
    rel_type: Mapped[WordRelationType] = mapped_column(enum_column(WordRelationType))


class SenseRelation(Base):
    __tablename__ = "sense_relations"
    __table_args__ = (
        UniqueConstraint("from_sense_id", "to_word_id", "rel_type"),
        Index(
            "ix_sense_relations_target_pending",
            "to_word_id",
            "id",
            postgresql_where=text("resolve_attempted_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_sense_id: Mapped[int] = mapped_column(ForeignKey("senses.id", ondelete="CASCADE"))
    to_word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"), index=True)
    to_sense_id: Mapped[int | None] = mapped_column(
        ForeignKey("senses.id", ondelete="SET NULL"), index=True
    )
    rel_type: Mapped[SenseRelationType] = mapped_column(enum_column(SenseRelationType))
    target_hash: Mapped[str | None] = mapped_column(String(64))
    resolve_attempted_at: Mapped[str | None] = mapped_column(String(32))


class Translation(Base):
    __tablename__ = "translations"
    __table_args__ = (UniqueConstraint("input_hash", "target_language"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    target_language: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
