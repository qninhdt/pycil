"""Disposable lexical and account fixtures for actual-stack browser tests."""

from datetime import UTC, datetime, timedelta

from pycil.account.models import UsagePeriod, User
from pycil.account.plans import Plan
from pycil.account.usage import period_bounds
from pycil.library.tree import provision_library
from pycil.study.artifacts.schemas import Artifact
from pycil.study.artifacts.storage import append
from pycil.study.enums import QuestionArtifactType as Kind
from pycil.study.models import UserSense
from pycil.vocabulary.enums import (
    EntryType,
    GenerationState,
    Inflection,
    PartOfSpeech,
    Tier,
    WordRelationType,
)
from pycil.vocabulary.models import (
    Collocation,
    Definition,
    Example,
    Sense,
    SenseForm,
    SensePattern,
    Word,
    WordAlias,
    WordRelation,
)
from sqlalchemy import text


def payloads(lemma, definition, variant=0):
    others = ["shop", "orchard", "factory"]
    meanings = [
        "a place to buy goods",
        "a place where fruit trees grow",
        "a place where goods are manufactured",
    ]
    return {
        Kind.WORD_DEFINITION: {
            "corrects": [definition],
            "distractors": [
                dict(word=w, definition=d) for w, d in zip(others, meanings, strict=True)
            ],
        },
        Kind.WORD_TO_USAGE: {
            "corrects": [f"She visited the [{lemma}]."],
            "distractors": [f"The [{lemma}] is a kind of {w}." for w in others],
        },
        Kind.CONTEXT_WORD_MEANING: {
            "context": f"She deposited money at the _ on day {variant + 1}.",
            "correct": {"expression": lemma, "meaning": definition},
            "distractors": [
                dict(expression=w, meaning=d) for w, d in zip(others, meanings, strict=True)
            ],
        },
        Kind.CONTEXT_TO_WORD: {
            "context": f"A customer wants to deposit money safely on day {variant + 1}.",
            "distractors": others,
        },
        Kind.DIALOGUE_COMPLETION: {
            "conversation": [
                {"A": f"Where is my money on day {variant + 1}?"},
                {"B": f"At the [{lemma}]."},
                {"A": "Is it safe?"},
                {"B": "Yes, it is."},
            ],
            "completion_points": [
                {
                    "turn_index": 1,
                    "distractors": [f"The [{lemma}] is a kind of {w}." for w in others],
                }
            ],
        },
        Kind.SENTENCE_REWRITE: {
            "source": f"She deposited her money safely on day {variant + 1}.",
            "correct": f"She put her money in the [{lemma}].",
            "distractors": [f"She ate the [{lemma}] with {w}." for w in others],
        },
    }


async def seed(sessions, identities, config):
    now = datetime.now(UTC)
    async with sessions() as session, session.begin():
        session.add_all(
            [
                Word(
                    id=1,
                    lemma="bank",
                    match_key="bank",
                    entry_type=EntryType.WORD,
                    generation_state=GenerationState.DONE,
                ),
                Word(
                    id=2,
                    lemma="archive",
                    match_key="archive",
                    entry_type=EntryType.WORD,
                    generation_state=GenerationState.DONE,
                ),
            ]
        )
        await session.flush()
        for identifier in [*range(1, 33), *range(100, 201)]:
            lemma = "bank" if identifier < 100 else "archive"
            verb = identifier == 2
            definition = (
                "to deposit money in a financial institution"
                if verb
                else "a financial institution"
                if lemma == "bank"
                else "a collection of historical documents"
            )
            if identifier == 32:
                definition = "an institution whose questions are initially unavailable"
            session.add(
                Sense(
                    id=identifier,
                    word_id=1 if lemma == "bank" else 2,
                    pos=PartOfSpeech.VERB if verb else PartOfSpeech.NOUN,
                    tier=Tier.CORE,
                )
            )
            await session.flush()
            session.add_all(
                [
                    Definition(sense_id=identifier, theme_id=None, content=definition),
                    Example(
                        sense_id=identifier,
                        theme_id=None,
                        content=f"I visited the [{lemma}].",
                    ),
                ]
            )
        session.add_all(
            [
                WordAlias(word_id=1, content="bank-alt", match_key="bank-alt"),
                SenseForm(
                    sense_id=2,
                    surface="banking",
                    inf=Inflection.ING,
                    match_key="banking",
                    head_key="banking",
                ),
                SensePattern(sense_id=2, content="bank {sth}", head_key="bank"),
                Collocation(sense_id=2, content="bank a cheque"),
                WordRelation(from_word_id=1, to_word_id=2, rel_type=WordRelationType.WORD_FAMILY),
            ]
        )
        for label, subject in identities.items():
            user = User(
                clerk_subject=subject,
                display_name="E2E learner " + label,
                plan=Plan.PRO if label == "B" else Plan.FREE,
                cycle_anchor=now,
            )
            session.add(user)
            await session.flush()
            await provision_library(session, user.id)
            if label == "C":
                start, end = period_bounds(user.cycle_anchor, now)
                units = config.plans[Plan.FREE].monthly_allowance_units
                session.add(
                    UsagePeriod(
                        user_id=user.id,
                        period_start=start,
                        period_end=end,
                        allowance_units=units,
                        used_units=units,
                    )
                )
            if label == "A":
                session.add(
                    UserSense(
                        user_id=user.id,
                        sense_id=30,
                        stability=1,
                        difficulty=5,
                        last_exposure_at=now - timedelta(days=3),
                        due_at=now - timedelta(days=1),
                        elo=600,
                        review_count=1,
                        lapse_count=0,
                    )
                )
        for table in ["words", "senses"]:
            await session.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"(SELECT max(id) FROM {table}))"
                )
            )
    artifacts = []
    for identifier in range(1, 31):
        for variant in range(2):
            for kind, payload in payloads("bank", "a financial institution", variant).items():
                artifacts.append(
                    Artifact(
                        id=0,
                        sense_id=identifier,
                        theme_id=None,
                        artifact_type=kind,
                        payload=payload,
                    )
                )
    await append(sessions, artifacts)
