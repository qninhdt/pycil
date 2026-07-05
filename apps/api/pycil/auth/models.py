"""Auth ORM models. Stateless JWT — no Session table.

Revocation is a ``token_version`` bump (bumped on ban/logout-all); the refresh
endpoint reissues against the current version. ``role`` is re-read from the DB
on every gated request (JWT claim is edge-convenience only).
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, text
from sqlmodel import Column, Field, SQLModel

TZDateTime = DateTime(timezone=True)


class UserRole(str, Enum):
    # Member name == value so the native PG enum label matches the JSON value.
    user = "user"
    admin = "admin"


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
    role: UserRole = Field(default=UserRole.user)
    banned_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    ban_reason: str | None = None
    # Bumped on ban/revoke/logout-all. BigInteger (smallint overflows at 32767).
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
