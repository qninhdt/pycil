"""Aggregate import of every ORM model so Alembic sees one metadata.

Import this module (not individual domain models) in ``alembic/env.py``.
"""

from sqlmodel import SQLModel

from pycil.assistant.infra.models import (  # noqa: F401
    AssistantAction,
    AssistantActionAudit,
    AssistantRun,
    AssistantRunEvent,
    AssistantThread,
)
from pycil.auth.models import RefreshSession, User  # noqa: F401
from pycil.content.infra.models import DeckSense  # noqa: F401
from pycil.hierarchy.infra.models import (  # noqa: F401
    DeckAttributes,
    Node,
)
from pycil.learning.infra.models import (  # noqa: F401
    Response,
    ReviewLog,
    SessionSummary,
    UserLearningSettings,
)
from pycil.policy.sense_state import UserSenseStats  # noqa: F401
from pycil.tasks.infra.models import (  # noqa: F401
    AsyncCommandReceipt,
    AsyncTask,
    AsyncTaskEvent,
    AsyncTaskInterest,
    AsyncTaskOutbox,
)

target_metadata = SQLModel.metadata
