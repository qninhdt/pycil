"""Auth ORM models.

Clerk issues and validates sessions; Pycil stores no session or refresh state of
its own. What remains here is the account row that every product foreign key
points at, plus the unique mapping from a Clerk subject to it.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, text
from sqlmodel import Field, SQLModel

TZDateTime = DateTime(timezone=True)


class User(SQLModel, table=True):
    """One Pycil account.

    ``id`` is the permanent key: nodes, responses, reviews, assistant threads and
    the credit ledger all reference it, and it does not change when the sign-in
    provider does. ``clerk_id`` is the stable Clerk subject, unique so a subject
    can never map to two accounts. It stays nullable because rows created before
    the provider cutover have no subject until their owner signs in again.
    """

    __tablename__ = "users"

    id: UUID | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
        primary_key=True,
    )
    clerk_id: str | None = Field(default=None, unique=True, index=True, max_length=64)
    email: str = Field(unique=True, index=True)
    name: str | None = None
    image: str | None = None
    created_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
    updated_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
