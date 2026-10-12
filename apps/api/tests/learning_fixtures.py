"""Initial quiz diagnostics for real stored artifacts in integration fixtures."""

from datetime import UTC, datetime


def quiz_result(artifact_id, correct=True, answered_at=None):
    return dict(
        question_artifact_id=artifact_id,
        question_type="DEFINITION_TO_WORD",
        format="SINGLE_CHOICE",
        diagnostics=dict(correct=correct),
        answered_at=answered_at or datetime.now(UTC).isoformat(),
    )
