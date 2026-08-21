"""Cross-service async-task contract: pure data, no I/O.

Public API shared by the API producers and the arq worker:
- task-kind constants and the kind → job-name registry
- typed dispatch payloads with ``to_dispatch``/``from_dispatch``
- the worker heartbeat key both services read
"""

from shared.tasks.contract import (
    JOB_NAME_FOR_KIND,
    JOB_NAME_GRADE_ANSWER_V1,
    TASK_KIND_GRADING,
    TASK_KIND_QUESTION_SUPPLY,
    TASK_KIND_WORD,
    WORKER_HEARTBEAT_KEY,
    WORKER_HEARTBEAT_TTL_SECONDS,
    GradingDispatch,
    SupplyDispatch,
    WordDispatch,
)

__all__ = [
    "GradingDispatch",
    "JOB_NAME_FOR_KIND",
    "JOB_NAME_GRADE_ANSWER_V1",
    "SupplyDispatch",
    "TASK_KIND_GRADING",
    "TASK_KIND_QUESTION_SUPPLY",
    "TASK_KIND_WORD",
    "WORKER_HEARTBEAT_KEY",
    "WORKER_HEARTBEAT_TTL_SECONDS",
    "WordDispatch",
]
