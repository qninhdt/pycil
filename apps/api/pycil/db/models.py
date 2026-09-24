"""Aggregate import of every ORM model so Alembic sees one metadata.

Import this module (not individual domain models) in ``alembic/env.py``.
"""

from sqlmodel import SQLModel

from pycil.account.models import CreditDebit, UserCredit  # noqa: F401
from pycil.assistant.infra.models import AssistantThread  # noqa: F401
from pycil.auth.models import User  # noqa: F401
from pycil.content.infra.models import DeckSense  # noqa: F401
from pycil.hierarchy.infra.models import Node  # noqa: F401
from pycil.learning.models import (  # noqa: F401
    Response,
    ReviewLog,
    SessionSummary,
    UserLearningSettings,
)
from pycil.policy.sense_state import UserSenseStats  # noqa: F401

target_metadata = SQLModel.metadata

