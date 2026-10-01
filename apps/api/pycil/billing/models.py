"""SQLModel models for account plan, usage periods, and usage events."""

from datetime import datetime
from uuid import UUID, uuid7

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

TZDateTime = DateTime(timezone=True)


class AccountPlan(SQLModel, table=True):
    __tablename__ = "account_plans"
    __table_args__ = (CheckConstraint("plan_key IN ('free', 'pro')", name="ck_account_plans_plan"),)

    user_id: UUID = Field(
        sa_column=Column(
            Uuid(),
            ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    plan_key: str = Field(sa_column=Column(String(16), nullable=False))
    cycle_anchor: datetime = Field(sa_type=TZDateTime, nullable=False)
    updated_at: datetime = Field(
        sa_type=TZDateTime,
        sa_column_kwargs={"server_default": text("NOW()")},
        nullable=False,
    )


class UsagePeriod(SQLModel, table=True):
    __tablename__ = "usage_periods"
    __table_args__ = (
        UniqueConstraint("user_id", "period_start", name="uq_usage_periods_user_period_start"),
        CheckConstraint("period_end > period_start", name="ck_usage_periods_time"),
        CheckConstraint("allowance_units >= 0", name="ck_usage_periods_allowance"),
        CheckConstraint("used_units >= 0", name="ck_usage_periods_used"),
        CheckConstraint("plan_key IN ('free', 'pro')", name="ck_usage_periods_plan"),
        Index("ix_usage_periods_user_end", "user_id", text("period_end DESC")),
    )

    id: UUID = Field(
        default_factory=uuid7,
        sa_column_kwargs={"server_default": text("uuidv7()")},
        primary_key=True,
    )
    user_id: UUID = Field(
        sa_column=Column(
            Uuid(),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    plan_key: str = Field(sa_column=Column(String(16), nullable=False))
    period_start: datetime = Field(sa_type=TZDateTime, nullable=False)
    period_end: datetime = Field(sa_type=TZDateTime, nullable=False)
    allowance_units: int = Field(sa_column=Column(BigInteger, nullable=False))
    used_units: int = Field(
        default=0, sa_column=Column(BigInteger, nullable=False, server_default=text("0"))
    )
    created_at: datetime = Field(
        sa_type=TZDateTime,
        sa_column_kwargs={"server_default": text("NOW()")},
        nullable=False,
    )
    updated_at: datetime = Field(
        sa_type=TZDateTime,
        sa_column_kwargs={"server_default": text("NOW()")},
        nullable=False,
    )

    @property
    def raw_remaining_units(self) -> int:
        return self.allowance_units - self.used_units

    @property
    def remaining_units(self) -> int:
        return max(0, self.raw_remaining_units)


class UsageEvent(SQLModel, table=True):
    __tablename__ = "usage_events"
    __table_args__ = (
        UniqueConstraint("event_key", name="uq_usage_events_event_key"),
        CheckConstraint("units > 0", name="ck_usage_events_units"),
        Index("ix_usage_events_period_created", "period_id", "created_at"),
    )

    id: UUID = Field(
        default_factory=uuid7,
        sa_column_kwargs={"server_default": text("uuidv7()")},
        primary_key=True,
    )
    period_id: UUID = Field(
        sa_column=Column(
            Uuid(),
            ForeignKey("usage_periods.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    event_key: str = Field(sa_column=Column(Text, nullable=False))
    feature_key: str = Field(sa_column=Column(String(64), nullable=False))
    units: int = Field(sa_column=Column(BigInteger, nullable=False))
    occurred_at: datetime = Field(sa_type=TZDateTime, nullable=False)
    details: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    created_at: datetime = Field(
        sa_type=TZDateTime,
        sa_column_kwargs={"server_default": text("NOW()")},
        nullable=False,
    )
