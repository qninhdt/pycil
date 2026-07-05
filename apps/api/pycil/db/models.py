"""Aggregate import of every ORM model so Alembic sees one metadata.

Import this module (not individual domain models) in ``alembic/env.py``.
"""

from pycil.auth.models import User  # noqa: F401
from pycil.content.models import DeckSense  # noqa: F401
from pycil.db.base import SQLModel
from pycil.hierarchy.models import (  # noqa: F401
    DeckAttributes,
    FolderAttributes,
    Node,
    UserNode,
)
from pycil.learning.models import (  # noqa: F401
    Response,
    ReviewLog,
    UserSenseStats,
)

target_metadata = SQLModel.metadata
