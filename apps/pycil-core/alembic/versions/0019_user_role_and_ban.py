"""User role + ban columns; widen token_version SmallInteger→Integer.

Revision ID: 0019_user_role_and_ban
Revises: 0018_backup_rehearsals

Adds:
- `user_role_enum` ('user','admin') native PG enum (precedent: classroom_role_enum, 0014).
- `users.role`        NOT NULL DEFAULT 'user'
- `users.banned_at`   TIMESTAMPTZ NULL
- `users.ban_reason`  TEXT NULL
- widens `users.token_version` SMALLINT → INTEGER (ban/revoke/soft-delete all
  bump it; smallint overflows at 32767).

NOTE on rollback ordering (README Phase 8): `get_current_user` reads `role`
on every authed request, so `alembic downgrade -1` MUST run AFTER swapping the
image back to a pre-0019 build — otherwise the dropped `role` column 500s every
authenticated request.
"""
from __future__ import annotations

from alembic import op


revision = "0019_user_role_and_ban"
down_revision = "0018_backup_rehearsals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          CREATE TYPE user_role_enum AS ENUM ('user', 'admin');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )
    op.execute(
        """
        ALTER TABLE users
          ADD COLUMN IF NOT EXISTS role user_role_enum NOT NULL DEFAULT 'user',
          ADD COLUMN IF NOT EXISTS banned_at TIMESTAMPTZ,
          ADD COLUMN IF NOT EXISTS ban_reason TEXT
        """
    )
    # Widen token_version smallint → integer (overflow at 32767 otherwise).
    op.execute(
        "ALTER TABLE users ALTER COLUMN token_version TYPE INTEGER"
    )
    # Partial index: admin lookups are rare but hot when they happen.
    op.execute(
        "CREATE INDEX IF NOT EXISTS users_role_admin "
        "ON users(role) WHERE role = 'admin'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS users_role_admin")
    op.execute("ALTER TABLE users ALTER COLUMN token_version TYPE SMALLINT")
    op.execute(
        "ALTER TABLE users "
        "DROP COLUMN IF EXISTS ban_reason, "
        "DROP COLUMN IF EXISTS banned_at, "
        "DROP COLUMN IF EXISTS role"
    )
    op.execute("DROP TYPE IF EXISTS user_role_enum")
