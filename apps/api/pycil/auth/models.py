"""Auth ORM models. Stateless JWT — no Session table.

Revocation is a ``token_version`` bump. The refresh endpoint reissues against
the current version; authorization is ownership- and visibility-based.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, text
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
