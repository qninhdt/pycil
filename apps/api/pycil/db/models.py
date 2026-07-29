"""Aggregate import of every ORM model so Alembic sees one metadata.

Import this module (not individual domain models) in ``alembic/env.py``.
"""

from pycil.assistant.models import (  # noqa: F401
    AssistantAction,
    AssistantActionAudit,
    AssistantRun,
    AssistantRunEvent,
    AssistantThread,
)
from pycil.auth.models import RefreshSession, User  # noqa: F401
from pycil.content.models import DeckSense  # noqa: F401
from pycil.db.base import SQLModel
from pycil.hierarchy.models import (  # noqa: F401
    DeckAttributes,
    Node,
)
from pycil.jobs.models import WordGeneration  # noqa: F401
from pycil.learning.models import (  # noqa: F401
    Response,
    ReviewLog,
    SessionSummary,
    UserLearningSettings,
    UserSenseStats,
)
from pycil.tasks.models import (  # noqa: F401
    AsyncCommandReceipt,
    AsyncTask,
    AsyncTaskDelivery,
    AsyncTaskEvent,
    AsyncTaskInterest,
    AsyncTaskOutbox,
)

target_metadata = SQLModel.metadata
