"""Shared SQLModel table mappings for the migrated Postgres schema."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, ENUM as PGEnum, INET, JSONB, UUID as PGUUID
from sqlmodel import Field, SQLModel

from shared.db.enums import (
    CefrLevel,
    ClassroomRole,
    NodeType,
    PartOfSpeech,
    ProfileVisibility,
    QuestionType,
    TermType,
    UserTermStatus,
    Visibility,
)


def _pg_enum(enum_type: type, name: str) -> PGEnum:
    return PGEnum(enum_type, name=name, create_type=False)


def _uuid_column(*, primary_key: bool = False, nullable: bool = True) -> Column[Any]:
    return Column(PGUUID(as_uuid=True), primary_key=primary_key, nullable=nullable)


def _dt_column(*, nullable: bool = True) -> Column[Any]:
    return Column(DateTime(timezone=True), nullable=nullable)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID | None = Field(default=None, sa_column=_uuid_column(primary_key=True, nullable=False))
    name: str | None = Field(default=None, sa_column=Column(Text))
    email: str = Field(sa_column=Column(Text, nullable=False))
    email_verified: datetime | None = Field(
        default=None,
        sa_column=Column("emailVerified", DateTime(timezone=True)),
    )
    image: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    updated_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    token_version: int = Field(default=0, sa_column=Column(SmallInteger, nullable=False))
    image_url: str | None = Field(default=None, sa_column=Column(Text))
    streak_days: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    last_session_date: date | None = Field(default=None, sa_column=Column(Date))
    xp_total: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    level: int = Field(default=1, sa_column=Column(SmallInteger, nullable=False))
    badges: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False),
    )
    league_rank: int = Field(default=0, sa_column=Column(SmallInteger, nullable=False))
    locale: str = Field(default="en", sa_column=Column(Text, nullable=False))
    bio: str | None = Field(default=None, sa_column=Column(Text))
    study_settings: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    deleted_at: datetime | None = Field(default=None, sa_column=_dt_column())
    stripe_customer_id: str | None = Field(default=None, sa_column=Column(Text))
    username: str | None = Field(default=None, sa_column=Column(Text))
    profile_visibility: ProfileVisibility = Field(
        default=ProfileVisibility.PRIVATE,
        sa_column=Column(_pg_enum(ProfileVisibility, "profile_visibility_enum"), nullable=False),
    )
    bio_public: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    streak_public: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    daily_goal: int = Field(default=20, sa_column=Column(SmallInteger, nullable=False))
    reminder_hour: int | None = Field(default=None, sa_column=Column(SmallInteger))


class Node(SQLModel, table=True):
    __tablename__ = "nodes"

    id: UUID | None = Field(default=None, sa_column=_uuid_column(primary_key=True, nullable=False))
    author_id: UUID = Field(sa_column=_uuid_column(nullable=False))
    type: NodeType = Field(
        sa_column=Column(_pg_enum(NodeType, "node_type"), nullable=False),
    )
    parent_node_id: UUID | None = Field(default=None, sa_column=_uuid_column())
    target_node_id: UUID | None = Field(default=None, sa_column=_uuid_column())
    name: str = Field(sa_column=Column(Text, nullable=False))
    description: str | None = Field(default=None, sa_column=Column(Text))
    visibility: Visibility = Field(
        default=Visibility.PRIVATE,
        sa_column=Column(_pg_enum(Visibility, "visibility"), nullable=False),
    )
    definition_count: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    likes_count: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    forks_count: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    updated_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class FolderAttribute(SQLModel, table=True):
    __tablename__ = "folder_attributes"

    node_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    subfolder_count: int = Field(default=0, sa_column=Column(Integer, nullable=False))


class DeckAttribute(SQLModel, table=True):
    __tablename__ = "deck_attributes"

    node_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    settings: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )


class Term(SQLModel, table=True):
    __tablename__ = "terms"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    type: TermType = Field(
        default=TermType.SINGLE_WORD,
        sa_column=Column(_pg_enum(TermType, "term_type"), nullable=False),
    )
    value: str = Field(sa_column=Column(Text, nullable=False))
    source: str = Field(default="manual", sa_column=Column(Text, nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    updated_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class Definition(SQLModel, table=True):
    __tablename__ = "definitions"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    term_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    frequency: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    cefr_level: CefrLevel | None = Field(
        default=None,
        sa_column=Column(_pg_enum(CefrLevel, "cefr_level")),
    )
    part_of_speech: PartOfSpeech | None = Field(
        default=None,
        sa_column=Column(_pg_enum(PartOfSpeech, "part_of_speech")),
    )
    synonyms: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(Text), nullable=False))
    antonyms: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(Text), nullable=False))
    hyponyms: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(Text), nullable=False))
    hypernyms: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(Text), nullable=False))
    meronyms: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(Text), nullable=False))
    holonyms: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(Text), nullable=False))
    homophones: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(Text), nullable=False))
    notes: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(Text), nullable=False))
    canonical_meaning: str | None = Field(default=None, sa_column=Column(Text))
    tags: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(Text), nullable=False))
    translation: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    tts_url: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    sense_index: int = Field(default=0, sa_column=Column(SmallInteger, nullable=False))
    disambiguator: str | None = Field(default=None, sa_column=Column(Text))
    is_primary: bool = Field(default=True, sa_column=Column(Boolean, nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    updated_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class DefinitionParaphrase(SQLModel, table=True):
    __tablename__ = "definition_paraphrases"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    definition_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    value: str = Field(sa_column=Column(Text, nullable=False))
    cefr_level: CefrLevel | None = Field(
        default=None,
        sa_column=Column(_pg_enum(CefrLevel, "cefr_level")),
    )
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    updated_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class TermExampleSentence(SQLModel, table=True):
    __tablename__ = "term_example_sentences"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    definition_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    value: str = Field(sa_column=Column(Text, nullable=False))
    cefr_level: CefrLevel | None = Field(
        default=None,
        sa_column=Column(_pg_enum(CefrLevel, "cefr_level")),
    )
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    updated_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class Question(SQLModel, table=True):
    __tablename__ = "questions"

    id: UUID | None = Field(default=None, sa_column=_uuid_column(primary_key=True, nullable=False))
    type: QuestionType = Field(
        sa_column=Column(_pg_enum(QuestionType, "question_type"), nullable=False),
    )
    definition_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    elo: int = Field(default=1000, sa_column=Column(Integer, nullable=False))
    variant_seed: int | None = Field(default=None, sa_column=Column(Integer))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    updated_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class Response(SQLModel, table=True):
    __tablename__ = "responses"

    id: UUID | None = Field(default=None, sa_column=_uuid_column(primary_key=True, nullable=False))
    user_id: UUID = Field(sa_column=_uuid_column(nullable=False))
    question_id: UUID = Field(sa_column=_uuid_column(nullable=False))
    is_correct: bool = Field(sa_column=Column(Boolean, nullable=False))
    user_answer: str | None = Field(default=None, sa_column=Column(Text))
    grade_reason: str | None = Field(default=None, sa_column=Column(Text))
    grade_confidence: float | None = Field(default=None, sa_column=Column(Numeric(asdecimal=False)))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class UserTermStat(SQLModel, table=True):
    __tablename__ = "user_term_stats"

    user_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    definition_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    mastery_score: int = Field(default=1000, sa_column=Column(Integer, nullable=False))
    mastery_level: int = Field(default=0, sa_column=Column(SmallInteger, nullable=False))
    last_review_date: datetime | None = Field(default=None, sa_column=_dt_column())
    next_review_date: datetime | None = Field(default=None, sa_column=_dt_column())
    review_count: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    interval_seconds: float = Field(default=0.0, sa_column=Column(Float, nullable=False))
    status: UserTermStatus = Field(
        default=UserTermStatus.ACTIVE,
        sa_column=Column(_pg_enum(UserTermStatus, "user_term_status"), nullable=False),
    )
    buried_until: date | None = Field(default=None, sa_column=Column(Date))
    lapse_count: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    updated_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class UserNode(SQLModel, table=True):
    __tablename__ = "user_nodes"

    user_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    node_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    is_starred: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    is_pinned: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    updated_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class DeckDefinition(SQLModel, table=True):
    __tablename__ = "deck_definitions"

    deck_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    definition_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    position: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class DeckTerm(SQLModel, table=True):
    __tablename__ = "deck_terms"

    deck_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    term_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    position: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: UUID | None = Field(default=None, sa_column=_uuid_column(primary_key=True, nullable=False))
    type: str = Field(sa_column=Column(Text, nullable=False))
    status: str = Field(default="pending", sa_column=Column(Text, nullable=False))
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    error: str | None = Field(default=None, sa_column=Column(Text))
    events: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    updated_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    created_by_user_id: UUID | None = Field(default=None, sa_column=_uuid_column())


class UserTermJob(SQLModel, table=True):
    __tablename__ = "user_term_jobs"

    user_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    term_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    job_id: UUID = Field(sa_column=_uuid_column(nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    last_event: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    last_llm_response: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    last_llm_response_at: datetime | None = Field(default=None, sa_column=_dt_column())


class Notification(SQLModel, table=True):
    __tablename__ = "notifications"

    id: UUID | None = Field(default=None, sa_column=_uuid_column(primary_key=True, nullable=False))
    user_id: UUID = Field(sa_column=_uuid_column(nullable=False))
    kind: str = Field(sa_column=Column(Text, nullable=False))
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    read_at: datetime | None = Field(default=None, sa_column=_dt_column())
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class DeckClone(SQLModel, table=True):
    __tablename__ = "deck_clones"

    id: UUID | None = Field(default=None, sa_column=_uuid_column(primary_key=True, nullable=False))
    source_deck_id: UUID | None = Field(default=None, sa_column=_uuid_column())
    cloned_deck_id: UUID | None = Field(default=None, sa_column=_uuid_column())
    cloned_by_user: UUID = Field(sa_column=_uuid_column(nullable=False))
    cloned_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class ChatSession(SQLModel, table=True):
    __tablename__ = "chat_sessions"

    id: UUID | None = Field(default=None, sa_column=_uuid_column(primary_key=True, nullable=False))
    user_id: UUID = Field(sa_column=_uuid_column(nullable=False))
    deck_id: UUID | None = Field(default=None, sa_column=_uuid_column())
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    last_message_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    total_input_tokens: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    total_output_tokens: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    status: str = Field(default="active", sa_column=Column(Text, nullable=False))


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: UUID | None = Field(default=None, sa_column=_uuid_column(primary_key=True, nullable=False))
    session_id: UUID = Field(sa_column=_uuid_column(nullable=False))
    role: str = Field(sa_column=Column(Text, nullable=False))
    content: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class TestRun(SQLModel, table=True):
    __tablename__ = "test_runs"

    id: UUID | None = Field(default=None, sa_column=_uuid_column(primary_key=True, nullable=False))
    user_id: UUID = Field(sa_column=_uuid_column(nullable=False))
    deck_id: UUID | None = Field(default=None, sa_column=_uuid_column())
    question_count: int = Field(sa_column=Column(SmallInteger, nullable=False))
    correct_count: int | None = Field(default=None, sa_column=Column(SmallInteger))
    started_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    completed_at: datetime | None = Field(default=None, sa_column=_dt_column())
    score_pct: float | None = Field(default=None, sa_column=Column(Numeric(asdecimal=False)))


class TestRunItem(SQLModel, table=True):
    __tablename__ = "test_run_items"

    id: UUID | None = Field(default=None, sa_column=_uuid_column(primary_key=True, nullable=False))
    run_id: UUID = Field(sa_column=_uuid_column(nullable=False))
    question_id: UUID = Field(sa_column=_uuid_column(nullable=False))
    answered_at: datetime | None = Field(default=None, sa_column=_dt_column())
    user_answer: str | None = Field(default=None, sa_column=Column(Text))
    is_correct: bool | None = Field(default=None, sa_column=Column(Boolean))
    position: int = Field(sa_column=Column(SmallInteger, nullable=False))


class Subscription(SQLModel, table=True):
    __tablename__ = "subscriptions"

    id: UUID | None = Field(default=None, sa_column=_uuid_column(primary_key=True, nullable=False))
    user_id: UUID = Field(sa_column=_uuid_column(nullable=False))
    tier: str = Field(default="free", sa_column=Column(Text, nullable=False))
    stripe_subscription_id: str | None = Field(default=None, sa_column=Column(Text))
    current_period_end: datetime | None = Field(default=None, sa_column=_dt_column())
    status: str = Field(default="active", sa_column=Column(Text, nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    updated_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    last_event_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    last_event_id: str = Field(default="", sa_column=Column(Text, nullable=False))


class StripeWebhookEvent(SQLModel, table=True):
    __tablename__ = "stripe_webhook_events"

    event_id: str = Field(primary_key=True)
    received_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class NodeShareLink(SQLModel, table=True):
    __tablename__ = "node_share_links"

    id: UUID | None = Field(default=None, sa_column=_uuid_column(primary_key=True, nullable=False))
    node_id: UUID = Field(sa_column=_uuid_column(nullable=False))
    token: str = Field(sa_column=Column(Text, nullable=False))
    created_by: UUID = Field(sa_column=_uuid_column(nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    revoked_at: datetime | None = Field(default=None, sa_column=_dt_column())


class FeatureFlag(SQLModel, table=True):
    __tablename__ = "feature_flags"

    name: str = Field(primary_key=True)
    rollout_percentage: int = Field(default=0, sa_column=Column(SmallInteger, nullable=False))
    enabled_user_ids: list[UUID] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(PGUUID(as_uuid=True)), nullable=False),
    )
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    updated_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    updated_by: UUID | None = Field(default=None, sa_column=_uuid_column())


class UserDefinitionStat(SQLModel, table=True):
    __tablename__ = "user_definition_stats"

    user_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    definition_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    elo: int = Field(default=800, sa_column=Column(Integer, nullable=False))
    total_seen: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    total_correct: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    last_seen_at: datetime | None = Field(default=None, sa_column=_dt_column())
    status: str = Field(default="active", sa_column=Column(Text, nullable=False))
    buried_until: date | None = Field(default=None, sa_column=Column(Date))
    lapse_count: int = Field(default=0, sa_column=Column(Integer, nullable=False))


class DefinitionOverride(SQLModel, table=True):
    __tablename__ = "definition_overrides"

    user_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    term_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    payload: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    updated_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class DeckLike(SQLModel, table=True):
    __tablename__ = "deck_likes"

    user_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    deck_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    liked_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class Follow(SQLModel, table=True):
    __tablename__ = "follows"

    follower_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    followee_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    followed_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class Classroom(SQLModel, table=True):
    __tablename__ = "classrooms"

    id: UUID | None = Field(default=None, sa_column=_uuid_column(primary_key=True, nullable=False))
    owner_id: UUID = Field(sa_column=_uuid_column(nullable=False))
    name: str = Field(sa_column=Column(Text, nullable=False))
    join_code: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    max_students: int = Field(default=50, sa_column=Column(SmallInteger, nullable=False))


class ClassroomMember(SQLModel, table=True):
    __tablename__ = "classroom_members"

    classroom_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    user_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    role: ClassroomRole = Field(
        sa_column=Column(_pg_enum(ClassroomRole, "classroom_role_enum"), nullable=False),
    )
    joined_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class ClassroomDeck(SQLModel, table=True):
    __tablename__ = "classroom_decks"

    classroom_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    deck_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    assigned_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class DefinitionComment(SQLModel, table=True):
    __tablename__ = "definition_comments"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    definition_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    author_id: UUID = Field(sa_column=_uuid_column(nullable=False))
    body: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    deleted_at: datetime | None = Field(default=None, sa_column=_dt_column())


class TermNote(SQLModel, table=True):
    __tablename__ = "term_notes"

    user_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    term_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    body: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    updated_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class AdminAction(SQLModel, table=True):
    __tablename__ = "admin_actions"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    actor_user_id: UUID = Field(sa_column=_uuid_column(nullable=False))
    target_user_id: UUID | None = Field(default=None, sa_column=_uuid_column())
    action: str = Field(sa_column=Column(Text, nullable=False))
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSONB, nullable=False),
    )
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    ip_address: str | None = Field(default=None, sa_column=Column(INET))
    user_agent: str | None = Field(default=None, sa_column=Column(Text))


class EmailEvent(SQLModel, table=True):
    __tablename__ = "email_events"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    provider: str = Field(sa_column=Column(Text, nullable=False))
    message_id: str = Field(sa_column=Column(Text, nullable=False))
    event: str = Field(sa_column=Column(Text, nullable=False))
    user_id: UUID | None = Field(default=None, sa_column=_uuid_column())
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    received_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class TosVersion(SQLModel, table=True):
    __tablename__ = "tos_versions"

    version: str = Field(primary_key=True)
    summary: str = Field(sa_column=Column(Text, nullable=False))
    body_md: str = Field(sa_column=Column(Text, nullable=False))
    effective_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class UserTosAck(SQLModel, table=True):
    __tablename__ = "user_tos_acks"

    user_id: UUID = Field(sa_column=_uuid_column(primary_key=True, nullable=False))
    version: str = Field(sa_column=Column(Text, primary_key=True))
    acked_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class SavedSearch(SQLModel, table=True):
    __tablename__ = "saved_searches"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    user_id: UUID = Field(sa_column=_uuid_column(nullable=False))
    name: str = Field(sa_column=Column(Text, nullable=False))
    filter_json: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    updated_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class PushSubscription(SQLModel, table=True):
    __tablename__ = "push_subscriptions"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    user_id: UUID = Field(sa_column=_uuid_column(nullable=False))
    endpoint: str = Field(sa_column=Column(Text, nullable=False))
    p256dh: str = Field(sa_column=Column(Text, nullable=False))
    auth: str = Field(sa_column=Column(Text, nullable=False))
    user_agent: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))
    last_used_at: datetime | None = Field(default=None, sa_column=_dt_column())


class ActivityEvent(SQLModel, table=True):
    __tablename__ = "activity_events"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    user_id: UUID = Field(sa_column=_uuid_column(nullable=False))
    kind: str = Field(sa_column=Column(Text, nullable=False))
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_dt_column(nullable=False))


class BackupRehearsal(SQLModel, table=True):
    __tablename__ = "backup_rehearsals"

    backup_id: str = Field(primary_key=True)
    rehearsed_at: datetime = Field(sa_column=_dt_column(nullable=False))
    status: str = Field(sa_column=Column(Text, nullable=False))
    rows_users: int | None = Field(default=None, sa_column=Column(Integer))
    rows_decks: int | None = Field(default=None, sa_column=Column(Integer))
    rows_terms: int | None = Field(default=None, sa_column=Column(Integer))
    error: str | None = Field(default=None, sa_column=Column(Text))
