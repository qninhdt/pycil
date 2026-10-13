"""Minimal valid payloads for the six retained exercise banks."""

from types import SimpleNamespace

from pycil.study.enums import QuestionArtifactType as Kind
from pycil.vocabulary.enums import Inflection


def lexical_target():
    word = SimpleNamespace(lemma="bank", aliases=["lender"])
    sense = SimpleNamespace(
        id=7,
        forms=[SimpleNamespace(surface="banks", inf=Inflection.PLURAL)],
        patterns=[],
        definition=SimpleNamespace(content="a financial institution"),
    )
    return word, sense


def payloads():
    return {
        Kind.WORD_DEFINITION: {
            "corrects": ["a financial institution"],
            "distractors": [{"word": "shop", "definition": "a place to buy goods"}],
        },
        Kind.WORD_TO_USAGE: {
            "corrects": ["The [bank] holds deposits."],
            "distractors": ["The [bank] is a kind of fruit."],
        },
        Kind.CONTEXT_WORD_MEANING: {
            "context": "She deposited money at the _.",
            "correct": {"expression": "banks", "meaning": "financial institutions"},
            "distractors": [{"expression": "shops", "meaning": "retail businesses"}],
        },
        Kind.CONTEXT_TO_WORD: {
            "context": "A customer wants to deposit money safely.",
            "distractors": ["shop"],
        },
        Kind.DIALOGUE_COMPLETION: {
            "conversation": [
                {"A": "Where is my money?"},
                {"B": "At the [bank]."},
                {"A": "Is it safe?"},
                {"B": "Yes, it is."},
            ],
            "completion_points": [
                {"turn_index": 1, "distractors": ["The [bank] has no deposits."]}
            ],
        },
        Kind.SENTENCE_REWRITE: {
            "source": "She deposited her money safely.",
            "correct": "She put her money in the [bank].",
            "distractors": ["She ate the [bank]."],
        },
    }
