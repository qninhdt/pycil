"""Account plan and credit ledger ORM models."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Column, DateTime, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from pycil.account.plans import AccountPlan

TZDateTime = DateTime(timezone=True)


class UserCredit(SQLModel, table=True):
    __tablename__ = "user_credits"

    user_id: UUID = Field(foreign_key="users.id", primary_key=True)
    plan: AccountPlan = Field(default=AccountPlan.free)
    # The day and time this account's billing cycle is anchored to. Written once
    # when the row is created and never moved: every period boundary is derived
    # from it, so a cycle anchored on the 31st returns to the 31st after a short
    # month instead of drifting to the 28th permanently.
    period_anchor: datetime = Field(
        sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
    # Start of the period that `period_used` is measured against. Advances by one
    # calendar month per renewal; the ledger rows of a past period keep their own
    # reference and are never rewritten.
    period_start: datetime = Field(
        sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
    period_used: int = Field(
        default=0, sa_column=Column(BigInteger, nullable=False, server_default=text("0"))
    )
    topup_balance: int = Field(
        default=0, sa_column=Column(BigInteger, nullable=False, server_default=text("0"))
    )


class CreditDebit(SQLModel, table=True):
    __tablename__ = "credit_debits"
    __table_args__ = (
        UniqueConstraint("kind", "reference_id", name="uq_credit_debit_kind_reference"),
    )

    id: UUID | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
        primary_key=True,
    )
    user_id: UUID = Field(foreign_key="users.id", index=True)
    kind: str = Field(max_length=32)
    reference_id: UUID
    amount: int = Field(sa_column=Column(BigInteger, nullable=False))
    details: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    created_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
