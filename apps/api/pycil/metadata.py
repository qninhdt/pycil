"""Aggregate import of every ORM model so Alembic sees one metadata.

Import this module (not individual domain models) in ``alembic/env.py``.
"""

from sqlmodel import SQLModel

from pycil.account.user import User  # noqa: F401
from pycil.assistant.models import AssistantThread  # noqa: F401
from pycil.billing.models import (  # noqa: F401
    AccountPlan,
    UsageEvent,
    UsagePeriod,
)
from pycil.library.models import (
    DeckSense,  # noqa: F401
    Node,  # noqa: F401
)
from pycil.study.models import (  # noqa: F401
    Response,
    ReviewLog,
    SessionSummary,
    StudySession,
    UserLearningSettings,
    UserSenseStats,
)

target_metadata = SQLModel.metadata
