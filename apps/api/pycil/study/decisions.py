"Typed grading questions; Instructor owns request encoding and answer validation."

from typing import Annotated, Literal, overload

from instructor.decisions import Choice, Noul, Question
from pydantic import BaseModel, create_model

from pycil.infrastructure.llm import choice_model
from pycil.study.enums import QuestionType
from pycil.vocabulary.types import MeaningInventory

AccuracyChoice = (
    Annotated[
        Literal["accurate"],
        Choice(
            description=(
                "The material semantic information stated is compatible with the "
                "meaning and "
                "contains no important misconception."
            )
        ),
    ]
    | Annotated[
        Literal["mixed"],
        Choice(
            description=(
                "The answer demonstrates relevant understanding but also contains"
                " at least "
                "one material false, misleading, or unjustified semantic claim."
            )
        ),
    ]
    | Annotated[
        Literal["inaccurate"],
        Choice(
            description=(
                "The central semantic characterization is wrong or incompatible with the meaning."
            )
        ),
    ]
)

CoverageChoice = (
    Annotated[
        Literal["sufficient"],
        Choice(
            description=(
                "Enough defining semantic information is present to identify and "
                "understand "
                "the meaning without an important semantic gap."
            )
        ),
    ]
    | Annotated[
        Literal["partial"],
        Choice(
            description=(
                "The answer communicates genuine relevant meaning but omits an "
                "important "
                "distinction or defining component, leaving it too broad, vague, or "
                "incomplete."
            )
        ),
    ]
    | Annotated[
        Literal["minimal"],
        Choice(
            description=(
                "The answer provides little usable defining information, such as "
                "only a weak "
                "association, extremely general category, isolated example, or "
                "vacuous "
                "restatement."
            )
        ),
    ]
)

MeaningChoice = (
    Annotated[
        Literal["correct"],
        Choice(description="The target clearly expresses the required meaning in context."),
    ]
    | Annotated[
        Literal["approximate"],
        Choice(
            description=(
                "The target expresses meaning that is relevant to the required "
                "meaning but is"
                " incomplete, vague, or semantically imprecise."
            )
        ),
    ]
    | Annotated[
        Literal["wrong"],
        Choice(description="The target expresses a different or incompatible meaning."),
    ]
)

FormChoice = (
    Annotated[Literal["correct"], Choice(description="The target expression is correctly formed.")]
    | Annotated[
        Literal["spelling_error"],
        Choice(
            description=(
                "The intended target expression is clear but contains an orthographic error."
            )
        ),
    ]
    | Annotated[
        Literal["form_error"],
        Choice(
            description=(
                "The intended target expression is clear but its inflectional or "
                "fixed "
                "lexical form is incorrect for a reason other than spelling."
            )
        ),
    ]
)

PreservationChoice = (
    Annotated[
        Literal["preserved"],
        Choice(
            description=(
                "All material information and commitments in the source are "
                "retained, without"
                " conflicting claims or unsupported material additions."
            )
        ),
    ]
    | Annotated[
        Literal["partial"],
        Choice(
            description=(
                "The core proposition is retained without contradiction, but some"
                " secondary "
                "information or qualification is omitted or weakened."
            )
        ),
    ]
    | Annotated[
        Literal["changed"],
        Choice(
            description=(
                "A core proposition is omitted or changed, a material role or "
                "qualification "
                "is changed, an unsupported material claim is added, or the "
                "answer's meaning "
                "cannot be reliably established."
            )
        ),
    ]
)

SINGLE_WORD_TASKS = {
    QuestionType.DEFINITION_TO_WORD: Noul(
        instructions=(
            "Does the lexical expression clearly intended by `answer` "
            "accurately satisfy "
            "the definition in `question`? Accept a different lexical "
            "expression if it "
            "fully expresses the defined meaning. Ignore only clear spelling "
            "errors; do "
            "not repair other lexical or grammatical differences."
        ),
        when_true=("The intended lexical expression accurately satisfies the definition."),
        when_false=("The intended lexical expression does not accurately satisfy the definition."),
    ),
    QuestionType.CONTEXT_TO_WORD: Noul(
        instructions=(
            "Does the lexical expression clearly intended by `answer` "
            "naturally and "
            "semantically fit the situation in `question`? Accept a different"
            " expression "
            "if it genuinely fits. Ignore only clear spelling errors; do not "
            "otherwise "
            "repair or reinterpret the answer."
        ),
        when_true=("The intended lexical expression naturally and accurately fits the situation."),
        when_false=(
            "The intended lexical expression does not naturally and accurately fit the situation."
        ),
    ),
    QuestionType.CLOZE_TO_WORD: Noul(
        instructions=(
            "Would inserting the lexical expression intended by `answer` into"
            " the blank "
            "in `question` produce a natural, grammatical completion with the"
            " intended "
            "meaning and construction? Correct only a clear spelling-only "
            "error for this "
            "judgment. Do not repair inflection, derivation, particles, word "
            "order, or "
            "grammar."
        ),
        when_true="The intended lexical expression produces a valid completion.",
        when_false=("The intended lexical expression does not produce a valid completion."),
    ),
}


class SingleWordAssessment(BaseModel):
    task_fit: float

    spelling_error: Annotated[
        float,
        Noul(
            instructions=(
                "Does `answer` contain a clear spelling-only error in an otherwise "
                "recognizable intended lexical expression? Judge orthography "
                "only. Do not "
                "consider whether the intended expression correctly answers "
                "`question`. Do "
                "not count inflection, derivation, missing or incorrect "
                "particles, word "
                "order, or grammar as spelling errors."
            ),
            when_true=(
                "A recognizable intended lexical expression contains a clear spelling-only error."
            ),
            when_false="There is no clear spelling-only error.",
        ),
    ]


def single_word_model(kind: QuestionType) -> type[SingleWordAssessment]:
    return create_model(
        "SingleWordDecision",
        __base__=SingleWordAssessment,
        task_fit=(Annotated[float, SINGLE_WORD_TASKS[kind]], ...),
    )


SENSE_QUESTIONS = {
    "matched_sense": (
        (
            "Which listed meaning of `answer` best matches the meaning that "
            "`answer` "
            "expresses in `question`? Choose `no_candidate` if none of the "
            "listed "
            "meanings fits."
        ),
        (
            "None of the listed meanings matches the meaning expressed by the"
            " answer in the question."
        ),
    ),
    "defined_meaning": (
        (
            "Which listed sense of `word` does `answer` most clearly attempt "
            "to define? "
            "Select the best-supported intended sense even if the definition is "
            "incomplete, vague, or contains some semantic error. Choose "
            "`no_candidate` "
            "only when there is not enough semantic evidence to identify any "
            "listed "
            "sense."
        ),
        "No listed sense is reasonably identifiable from the answer.",
    ),
}


class MatchedSense(BaseModel):
    matched_sense: str


class DefinedMeaning(BaseModel):
    defined_meaning: str


@overload
def sense_selection_model(
    field_name: Literal["matched_sense"],
    word: MeaningInventory,
) -> type[MatchedSense]: ...


@overload
def sense_selection_model(
    field_name: Literal["defined_meaning"],
    word: MeaningInventory,
) -> type[DefinedMeaning]: ...


def sense_selection_model(
    field_name: Literal["matched_sense", "defined_meaning"],
    word: MeaningInventory,
) -> type[MatchedSense] | type[DefinedMeaning]:
    instructions, no_candidate = SENSE_QUESTIONS[field_name]
    criteria = {"no_candidate": no_candidate}
    criteria.update(
        {
            f"sense_{sense['id']}": f"{word['lemma']} - {sense['pos']} - {sense['definition']}"
            for sense in word["senses"]
        }
    )
    if field_name == "matched_sense":
        return choice_model(
            "MatchedSenseDecision", MatchedSense, field_name, instructions, criteria
        )
    return choice_model(
        "DefinedMeaningDecision", DefinedMeaning, field_name, instructions, criteria
    )


class DefinitionAssessment(BaseModel):
    accuracy: Annotated[
        AccuracyChoice,
        Question(
            instructions=(
                "How accurate is the semantic information stated in `answer` "
                "about `meaning`?"
                " Judge only whether the claims it makes are correct. Do not "
                "lower this "
                "rating because relevant information is missing. Ignore spelling,"
                " grammar, "
                "and wording quality."
            )
        ),
    ]
    coverage: Annotated[
        CoverageChoice,
        Question(
            instructions=(
                "How much of the defining semantic information in `meaning` is "
                "present in "
                "`answer`? Judge only what required meaning is present or "
                "missing. Do not "
                "lower this rating because information that is present is "
                "inaccurate. Accept "
                "a sufficiently precise synonym as sufficient."
            )
        ),
    ]


class TargetUseAssessment(BaseModel):
    used: Annotated[
        float,
        Noul(
            instructions=(
                "Does `answer` actually attempt to use `word` or one of its "
                "licensed forms? "
                "Count clear spelling or form errors as use when the intended "
                "target "
                "expression is still identifiable. Do not count synonyms or "
                "different lexical"
                " expressions."
            ),
            when_true="The target lexical expression is recognizably used or attempted.",
            when_false="The target lexical expression is not used.",
        ),
    ]


class UsageAssessment(BaseModel):
    meaning: Annotated[
        MeaningChoice,
        Question(
            instructions=(
                "How accurately does the target expression convey `meaning` in "
                "`answer`? "
                "Judge only the meaning expressed by the target in context. "
                "Ignore its form, "
                "syntactic construction, collocational conventionality, and "
                "appropriacy."
            )
        ),
    ]
    form: Annotated[
        FormChoice,
        Question(
            instructions=(
                "How accurately is the target lexical expression itself formed in"
                " `answer`? "
                "Judge only spelling, inflection, and required fixed lexical "
                "components. "
                "Ignore its meaning, syntactic construction, surrounding lexical "
                "combinations, and appropriacy."
            )
        ),
    ]
    construction: Annotated[
        float,
        Noul(
            instructions=(
                "Is the target expression used in a syntactically licensed "
                "construction in "
                "`answer`? Judge only target-specific grammatical behavior such "
                "as argument "
                "structure, complementation, transitivity, and syntactic "
                "placement. Ignore "
                "spelling, inflectional form errors, unrelated sentence grammar, "
                "collocation,"
                " and appropriacy."
            ),
            when_true="The syntactic construction involving the target is licensed.",
            when_false="The target is used in a syntactic construction it does not license.",
        ),
    ]
    collocation: Annotated[
        float,
        Noul(
            instructions=(
                "Are the lexical combinations involving the target expression in "
                "`answer` "
                "legitimate English for the intended meaning? Judge only "
                "combinations between"
                " the target and relevant surrounding lexical items. Ignore "
                "grammatical "
                "construction, general sentence style, and appropriacy. Accept less "
                "conventional, unusual, or context-dependent combinations when "
                "they are "
                "legitimate English."
            ),
            when_true=(
                "The target occurs in a conventional, unmarked lexical "
                "combination, or a "
                "legitimate less conventional, unusual, or context-dependent "
                "combination."
            ),
            when_false=(
                "The target is involved in a lexical combination that is not "
                "normally "
                "acceptable for the intended meaning."
            ),
        ),
    ]
    appropriacy: Annotated[
        float,
        Noul(
            instructions=(
                "Is the target expression appropriate for the communicative context "
                "established by `answer`? Judge only lexical constraints such as "
                "register, "
                "tone, social use, connotation, and domain. Do not penalize a "
                "word merely for"
                " being uncommon, and ignore meaning accuracy, form, syntax, and "
                "collocation."
                " Accept noticeably marked register, tone, connotation, or domain"
                " when the "
                "target remains usable; reject material conflicts with lexical "
                "usage "
                "constraints."
            ),
            when_true=(
                "The target fits the context, including noticeably marked but "
                "usable "
                "register, tone, connotation, or domain."
            ),
            when_false=(
                "The target conflicts with an important lexical usage constraint of the context."
            ),
        ),
    ]


class RewriteAssessment(UsageAssessment):
    meaning_preservation: Annotated[
        PreservationChoice,
        Question(
            instructions=(
                "How faithfully does `answer` preserve the meaning of `source`? "
                "Compare "
                "propositions, participant roles, negation, tense and time "
                "reference, "
                "modality, conditions, and degree where they affect meaning. "
                "Accept valid "
                "changes in wording, voice, clause structure, and word order. Do "
                "not require "
                "similarity to a reference rewrite. Assess target usage "
                "separately. Ignore "
                "spelling or grammar errors here when the intended meaning "
                "remains clear; "
                "account for them when they change meaning."
            )
        ),
    ]
