from datetime import UTC, datetime
from uuid import UUID, uuid7

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pycil.account.plans import Feature, Plan
from pycil.database import Base, enum_column


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("jsonb_typeof(settings) = 'object'", name="settings_object"),
        CheckConstraint("handle IS NULL OR handle ~ '^[a-z][a-z0-9_]{2,29}$'", name="handle_shape"),
        CheckConstraint(
            "display_name IS NULL OR (display_name = btrim(display_name) "
            "AND length(display_name) BETWEEN 1 AND 255)",
            name="display_name_shape",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    clerk_subject: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    handle: Mapped[str | None] = mapped_column(String(30), unique=True)
    bio: Mapped[str | None] = mapped_column(String(500))
    plan: Mapped[Plan] = mapped_column(enum_column(Plan), default=Plan.FREE)
    settings: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    cycle_anchor: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class UsagePeriod(Base):
    __tablename__ = "usage_periods"
    __table_args__ = (
        UniqueConstraint("user_id", "period_start"),
        CheckConstraint("allowance_units >= 0 AND used_units >= 0", name="nonnegative_units"),
        CheckConstraint("period_end > period_start", name="valid_period"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    allowance_units: Mapped[int] = mapped_column(BigInteger)
    used_units: Mapped[int] = mapped_column(BigInteger, default=0)


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (CheckConstraint("units >= 0", name="nonnegative_units"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    period_id: Mapped[UUID] = mapped_column(
        ForeignKey("usage_periods.id", ondelete="CASCADE"), index=True
    )
    execution_key: Mapped[UUID] = mapped_column(unique=True)
    feature: Mapped[Feature] = mapped_column(enum_column(Feature))
    units: Mapped[int] = mapped_column(BigInteger)
    unmetered_calls: Mapped[int] = mapped_column(default=0)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
