"""Opaque async-resource channels shared by API and worker.

Authorization is enforced by the Centrifugo subscribe proxy against persisted
interests, not by channel names or user-limited channel suffixes.
"""

from uuid import UUID

_ASYNC_NS = "async"

# Exported because the subscribe proxy parses incoming channel strings against
# the same prefix this builder emits; deriving both from one namespace is what
# keeps them equal.
ASYNC_TASK_PREFIX = f"{_ASYNC_NS}:"


def async_task(task_id: UUID | str) -> str:
    """Return the sole browser-visible channel form for a durable task."""
    return f"{ASYNC_TASK_PREFIX}{task_id}"
