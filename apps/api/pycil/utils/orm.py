"""SQLAlchemy model and row serialization utilities."""

from collections.abc import Iterable, Mapping
from enum import Enum
from typing import ClassVar, Protocol

from sqlalchemy.engine import RowMapping
from sqlalchemy.sql.selectable import FromClause


class HasTable(Protocol):
    __table__: ClassVar[FromClause]


def row_data(row: HasTable) -> dict[str, object]:
    """Serialize a SQLAlchemy mapped model instance to a dictionary, omitting computed columns."""
    return {
        str(column.name): getattr(row, str(column.name))
        for column in row.__table__.columns
        if column.computed is None
    }


def snapshot_values(
    row: Mapping[str, object] | RowMapping, exclude: Iterable[str] = ()
) -> dict[str, object]:
    return {
        str(k): v.value if isinstance(v, Enum) else v
        for k, v in row.items()
        if str(k) not in exclude
    }
