"""Opaque async-resource channels shared by API and worker.

Authorization is enforced by the Centrifugo subscribe proxy against persisted
interests, not by channel names or user-limited channel suffixes.
"""

from uuid import UUID

_ASYNC_NS = "async"


def async_task(task_id: UUID | str) -> str:
    """Return the sole browser-visible channel form for a durable task."""
    return f"{_ASYNC_NS}:{task_id}"
