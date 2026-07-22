"""Auth ORM models, including server-side rotating refresh sessions."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Index, text
from sqlmodel import Column, Field, SQLModel

TZDateTime = DateTime(timezone=True)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
        primary_key=True,
    )
    email: str = Field(unique=True, index=True)
    name: str | None = None
    image: str | None = None
    # Bumped when credentials must be revoked. BigInteger avoids smallint overflow.
    token_version: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False, server_default=text("0")),
    )
    created_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
    updated_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )


class RefreshSession(SQLModel, table=True):
    """One opaque refresh credential, persisted solely as a keyed digest."""

    __tablename__ = "refresh_sessions"
    __table_args__ = (
        Index("ix_refresh_sessions_user_active", "user_id", "revoked_at"),
        Index("ix_refresh_sessions_family", "family_id"),
    )

    id: UUID | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
        primary_key=True,
    )
    user_id: UUID = Field(foreign_key="users.id", index=True)
    family_id: UUID = Field(index=True)
    token_digest: str = Field(unique=True, index=True, max_length=64)
    expires_at: datetime = Field(sa_type=TZDateTime)
    revoked_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    replaced_by_id: UUID | None = Field(default=None, foreign_key="refresh_sessions.id")
    created_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
