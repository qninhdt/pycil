from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from pycil.app.config import load_config
from pycil.study.evidence import evidence, update_elo
from pycil.study.fsrs import next_state
from pycil.study.schemas import GradeResult


@pytest.mark.parametrize(
    "kind, fmt, diagnostics, expected",
    [
        ("definition_to_word", "single_choice", {"correct": False}, (7, 0.0, 0.0)),
        ("word_to_usage", "single_choice", {"correct": True}, (7, None, 1.0)),
        (
            "context_to_word",
            "single_word",
            {"task_fit": True, "spelling_error": True, "sense_id": 8},
            (8, 1.0, 0.8),
        ),
        (
            "context_to_word",
            "single_word",
            {"task_fit": False, "spelling_error": False, "sense_id": 8},
            (7, 0.0, 0.0),
        ),
        (
            "word_to_definition",
            "short_answer",
            {"sense_id": 8, "accuracy": "mixed", "coverage": "partial"},
            (8, 1.0, 0.25),
        ),
        (
            "word_to_definition",
            "short_answer",
            {"sense_id": 8, "accuracy": "accurate", "coverage": "minimal"},
            (7, 0.0, 0.0),
        ),
        (
            "word_to_usage",
            "short_answer",
            {
                "used": False,
                "meaning": None,
                "form": None,
                "construction": None,
                "collocation": None,
                "appropriacy": None,
            },
            (7, None, 0.0),
        ),
        (
            "sentence_rewrite",
            "short_answer",
            {
                "used": False,
                "meaning": None,
                "form": None,
                "construction": None,
                "collocation": None,
                "appropriacy": None,
                "meaning_preservation": None,
            },
            (7, 0.0, None),
        ),
        (
            "word_to_usage",
            "short_answer",
            {
                "used": True,
                "meaning": "approximate",
                "form": "spelling_error",
                "construction": True,
                "collocation": False,
                "appropriacy": True,
            },
            (7, None, 0.35),
        ),
        (
            "sentence_rewrite",
            "short_answer",
            {
                "used": True,
                "meaning": "correct",
                "form": "correct",
                "construction": True,
                "collocation": True,
                "appropriacy": True,
                "meaning_preservation": "partial",
            },
            (7, 1.0, 0.5),
        ),
        (
            "sentence_rewrite",
            "short_answer",
            {
                "used": True,
                "meaning": "wrong",
                "form": "correct",
                "construction": True,
                "collocation": True,
                "appropriacy": True,
                "meaning_preservation": "preserved",
            },
            (7, 0.0, None),
        ),
    ],
)
def test_diagnostic_evidence_credits_correct_sense_and_separates_recall_usage(
    kind, fmt, diagnostics, expected
):
    item = GradeResult(
        question_artifact_id=1, question_type=kind, format=fmt, diagnostics=diagnostics
    )
    actual = evidence(item, 7)
    assert actual[0] == expected[0]
    for score, wanted in zip(actual[1:], expected[1:], strict=True):
        if wanted is None:
            assert score is None
        else:
            assert score == pytest.approx(wanted)


def test_grouped_elo_shares_one_time_budget_and_handles_extreme_scores():
    policy = load_config().study.mastery
    now = datetime(2026, 1, 1, tzinfo=UTC)
    base = 1000.0
    full = update_elo(base, [(1.0, base)], None, now, policy)
    assert full == base + policy.k_elo / 2
    assert update_elo(base, [(1.0, base)] * 5, None, now, policy) == full
    assert update_elo(base, [(1.0, base)], now, now, policy) == base
    assert (
        update_elo(
            base, [(1.0, base)], now - timedelta(hours=policy.horizon_hours / 2), now, policy
        )
        == base + policy.k_elo / 4
    )
    assert update_elo(base, [(None, base)], None, now, policy) == base
    assert update_elo(1e10, [(0.0, -1e10)], None, now, policy) == 1e10 - policy.k_elo
    assert update_elo(-1e10, [(1.0, 1e10)], None, now, policy) == -1e10 + policy.k_elo


def test_fsrs_failure_in_mixed_batch_preserves_null_memory_and_caps_interval():
    config = load_config()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    good = next_state(None, [1.0], now, config.study.fsrs)
    again = next_state(None, [0.0], now, config.study.fsrs)
    assert good[0] > again[0] > 0
    assert next_state(None, [1.0, None, 0.0], now, config.study.fsrs) == again
    memory = SimpleNamespace(
        stability=20.0, difficulty=5.0, last_exposure_at=now - timedelta(days=3)
    )
    assert next_state(memory, [None, None], now, config.study.fsrs)[:2] == (20.0, 5.0)
    capped = config.model_copy(
        update={
            "study": config.study.model_copy(
                update={"fsrs": config.study.fsrs.model_copy(update={"max_interval_days": 1})}
            )
        }
    )
    assert next_state(memory, [None], now, capped.study.fsrs)[2] <= now + timedelta(days=1)
    assert next_state(memory, [1.0], now, config.study.fsrs)[2] > now
