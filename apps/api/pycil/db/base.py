"""SQLModel metadata base.

All ORM models import from here so Alembic autogenerate sees one metadata.
Domain models register by importing this module's ``SQLModel`` and declaring
tables; ``pycil.db.models`` (created in phase 2) aggregates them for migrations.
"""

from sqlmodel import SQLModel

__all__ = ["SQLModel"]
