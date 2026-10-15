from types import SimpleNamespace

import pytest

from pycil.app.config import load_config
from pycil.app.http import Problem
from pycil.study import preparation
from pycil.study.config import LearningPreferences
from pycil.study.enums import QuestionType, ResponseFormat


class Draws:
    def __init__(self):
        self.levels, self.weights = None, None

    def choices(self, levels, *, weights, k):
        self.levels, self.weights = levels, weights
        return [levels[-1]]

    def choice(self, pairs):
        return pairs[0]


def test_pair_planning_uses_weighted_eligible_levels_and_returns_requested_draws(monkeypatch):
    config, draws = load_config(), Draws()
    monkeypatch.setattr(preparation, "randomness", draws)
    selected = config.product.study.defaults
    result = preparation.plan_pairs(10000, selected, config, 3)
    assert len(result) == 3
    assert all(kind in selected.question_types and fmt in selected.formats for kind, fmt in result)
    level = config.product.study.mastery.level(10000)
    assert draws.weights == [2 ** (candidate - level) for candidate in draws.levels]
    assert all(
        config.product.study.pair_levels[kind][fmt] == max(draws.levels) for kind, fmt in result
    )


def test_pair_planning_falls_back_to_minimum_supported_level_and_rejects_infeasibility(monkeypatch):
    config, draws = load_config(), Draws()
    monkeypatch.setattr(preparation, "randomness", draws)
    selected = LearningPreferences(
        question_types=[QuestionType.SENTENCE_REWRITE],
        formats=[ResponseFormat.SHORT_ANSWER],
        max_sense_count=1,
        questions_per_sense=1,
    )
    assert preparation.plan_pairs(-10000, selected, config, 1) == [
        (QuestionType.SENTENCE_REWRITE, ResponseFormat.SHORT_ANSWER)
    ]
    assert draws.levels == [
        config.product.study.pair_levels[QuestionType.SENTENCE_REWRITE][ResponseFormat.SHORT_ANSWER]
    ]
    impossible = SimpleNamespace(
        question_types=[QuestionType.WORD_TO_USAGE], formats=[ResponseFormat.SINGLE_WORD]
    )
    with pytest.raises(Problem) as error:
        preparation.plan_pairs(1000, impossible, config, 1)
    assert error.value.code == "infeasible_learning_preferences"
