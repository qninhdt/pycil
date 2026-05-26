"""Compliance + retention helpers (P12 phases 3-5) + email infra (P4 phase 1).

Revision ID: 0016_compliance_email_infra
Revises: 0015_power_user_and_audit

- email_events    : Resend/Postmark webhook ledger
- tos_versions    : versioned ToS rollouts (P12 phase 3)
- user_tos_acks   : per-user ToS acknowledgements
- saved_searches  : smart-deck filter dataclasses (P5 phase 2)
"""
from __future__ import annotations

from alembic import op


revision = "0016_compliance_email_infra"
down_revision = "0015_power_user_and_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS email_events (
          id          BIGSERIAL PRIMARY KEY,
          provider    TEXT NOT NULL,
          message_id  TEXT NOT NULL,
          event       TEXT NOT NULL,
          user_id     UUID,
          payload     JSONB NOT NULL DEFAULT '{}',
          received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS email_events_msg_event "
        "ON email_events(provider, message_id, event)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tos_versions (
          version      TEXT PRIMARY KEY,
          summary      TEXT NOT NULL,
          body_md      TEXT NOT NULL,
          effective_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_tos_acks (
          user_id   UUID NOT NULL,
          version   TEXT NOT NULL REFERENCES tos_versions(version),
          acked_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (user_id, version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_searches (
          id          BIGSERIAL PRIMARY KEY,
          user_id     UUID NOT NULL,
          name        TEXT NOT NULL,
          filter_json JSONB NOT NULL,
          created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS saved_searches_user "
        "ON saved_searches(user_id, updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS saved_searches_user")
    op.execute("DROP TABLE IF EXISTS saved_searches")
    op.execute("DROP TABLE IF EXISTS user_tos_acks")
    op.execute("DROP TABLE IF EXISTS tos_versions")
    op.execute("DROP INDEX IF EXISTS email_events_msg_event")
    op.execute("DROP TABLE IF EXISTS email_events")
