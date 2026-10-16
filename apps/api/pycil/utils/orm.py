"""SQLAlchemy model and row serialization utilities."""

from typing import Any


def row_data(row: Any) -> dict[str, object]:
    """Serialize a SQLAlchemy mapped model instance to a dictionary, omitting computed columns."""
    return {
        str(column.name): getattr(row, str(column.name))
        for column in row.__table__.columns
        if column.computed is None
    }
