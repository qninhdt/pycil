"""Typed candidate selection for lexical relations."""

from pydantic import BaseModel

from pycil.infrastructure.llm import choice_model
from pycil.vocabulary.enums import SenseRelationType
from pycil.vocabulary.relations.storage import PendingLink

RELATION_RULES = {
    SenseRelationType.SYNONYM: (
        "The target sense must express essentially the same lexicalized "
        "concept as "
        "the source sense."
    ),
    SenseRelationType.ANTONYM: (
        "The target sense must express an opposing meaning to the source "
        "sense on the"
        " relevant semantic dimension."
    ),
    SenseRelationType.HYPERNYM: "The source sense must denote a kind or type of the target sense.",
    SenseRelationType.HYPONYM: "The target sense must denote a kind or type of the source sense.",
    SenseRelationType.MERONYM: (
        "The target sense must denote a part, member, or substance of "
        "what the source"
        " sense denotes."
    ),
    SenseRelationType.HOLONYM: (
        "What the source sense denotes must be a part, member, or "
        "substance of what "
        "the target sense denotes."
    ),
}


class RelationSelection(BaseModel):
    matched_sense: str


def relation_selection_model(link: PendingLink) -> type[RelationSelection]:
    criteria = {
        "no_candidate": (
            "No candidate sense forms the required semantic relation with the source sense."
        )
    }
    criteria.update(
        {
            f"candidate_{index}": f"{link.target_word} - {sense.pos.value} - {sense.definition}"
            for index, sense in enumerate(link.candidates, 1)
        }
    )
    return choice_model(
        "RelationSelectionDecision",
        RelationSelection,
        "matched_sense",
        (
            "Which candidate sense of target.word satisfies relation.rule "
            "with the source"
            " sense? Compare lexical meanings, not wording overlap or general "
            "association. Choose no_candidate if none forms the required "
            "relation. If "
            "several candidates qualify, choose the most directly equivalent "
            "endpoint."
        ),
        criteria,
    )
