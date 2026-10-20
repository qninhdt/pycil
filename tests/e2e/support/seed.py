"""Finite fixture preparation inside the disposable API image."""

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from pycil.account.models import UsagePeriod, User
from pycil.account.plans import Plan
from pycil.account.usage import period_bounds
from pycil.app.config import load_config
from pycil.app.schema import register_models
from pycil.infrastructure.database import connect
from pycil.study.artifacts.schemas import ARTIFACT_SCHEMAS, Artifact, validate_artifact
from pycil.study.artifacts.storage import append, generation_context
from pycil.study.enums import QuestionArtifactType
from pycil.study.models import UserSense
from pycil.vocabulary.enums import (
    EntryType,
    GenerationState,
    Inflection,
    PartOfSpeech,
    Tier,
)
from pycil.vocabulary.models import (
    Definition,
    Example,
    Sense,
    SenseForm,
    Word,
    WordAlias,
)
from pycil.vocabulary.revisions import baseline as baseline_content
from sqlalchemy import select


async def baseline(manifest: Path | None):
    register_models()
    rows = json.loads((Path(__file__).parent / "data/vocabulary.json").read_text())
    pagination = json.loads(
        (Path(__file__).parent / "data/pagination.json").read_text()
    )
    rows.extend(pagination)
    engine, sessions = connect(os.environ["DB_URL"])
    result = {}
    try:
        async with sessions() as session, session.begin():
            words = {}
            for row in rows:
                lemma = row["lemma"]
                if lemma not in words:
                    word = Word(
                        lemma=lemma,
                        match_key=lemma,
                        entry_type=EntryType.WORD,
                        generation_state=GenerationState.DONE,
                    )
                    session.add(word)
                    await session.flush()
                    words[lemma] = word
                    for alias in row.get("aliases", []):
                        session.add(
                            WordAlias(word_id=word.id, content=alias, match_key=alias)
                        )
                sense = Sense(
                    word_id=words[lemma].id,
                    pos=PartOfSpeech(row["pos"]),
                    tier=Tier.CORE,
                )
                session.add(sense)
                await session.flush()
                session.add(Definition(sense_id=sense.id, content=row["definition"]))
                if "example" in row:
                    session.add(Example(sense_id=sense.id, content=row["example"]))
                for form in row.get("forms", []):
                    session.add(
                        SenseForm(
                            sense_id=sense.id,
                            surface=form["surface"],
                            inf=Inflection(form["inf"]),
                            match_key=form["surface"],
                            head_key=lemma,
                        )
                    )
                result[row["key"]] = {"word_id": words[lemma].id, "sense_id": sense.id}
        questions = json.loads(
            (Path(__file__).parent / "data/questions.json").read_text()
        )
        artifacts = []
        for key, bank in questions.items():
            word, sense, _ = await generation_context(sessions, result[key]["sense_id"])
            for name, raw in bank.items():
                kind = QuestionArtifactType(name)
                payload = ARTIFACT_SCHEMAS[kind].model_validate(raw)
                validate_artifact(payload, kind, word, sense, 3, 1)
                artifacts.append(
                    Artifact(
                        id=0,
                        sense_id=sense.id,
                        theme_id=None,
                        artifact_type=kind,
                        payload=payload.model_dump(),
                    )
                )
        await baseline_content(sessions)
        await append(sessions, artifacts)
        result["pagination"] = [
            result.pop(row["key"])
            | {"lemma": row["lemma"], "definition": row["definition"]}
            for row in pagination
        ]
        print(json.dumps(result))
        if manifest is not None:
            manifest.write_text(json.dumps(result))
    finally:
        await engine.dispose()


async def user_state(
    identifier: UUID, plan: Plan | None, exhausted: bool, due_sense: int | None
):
    register_models()
    config = load_config()
    url = os.environ["DB_URL"]
    engine, sessions = connect(url)
    try:
        async with sessions() as session, session.begin():
            user = await session.get(User, identifier)
            if user is None:
                raise ValueError("User must be provisioned through the real API first")
            if plan is not None:
                user.plan = plan
            now = datetime.now(UTC)
            if exhausted:
                start, end = period_bounds(user.cycle_anchor, now)
                budget = config.account.plans[user.plan].monthly_allowance_units
                period = await session.scalar(
                    select(UsagePeriod).where(
                        UsagePeriod.user_id == identifier,
                        UsagePeriod.period_start == start,
                    )
                )
                if period is None:
                    period = UsagePeriod(
                        user_id=identifier,
                        period_start=start,
                        period_end=end,
                        allowance_units=budget,
                        used_units=budget,
                    )
                    session.add(period)
                else:
                    period.used_units = max(budget, period.allowance_units)
            if due_sense is not None:
                if await session.get(Sense, due_sense) is None:
                    raise ValueError("Unknown fixture sense")
                memory = await session.get(UserSense, (identifier, due_sense))
                if memory is None:
                    memory = UserSense(
                        user_id=identifier,
                        sense_id=due_sense,
                        stability=1,
                        difficulty=5,
                        elo=600,
                        review_count=1,
                        lapse_count=0,
                    )
                    session.add(memory)
                memory.last_exposure_at = now - timedelta(days=2)
                memory.due_at = now - timedelta(days=1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["baseline", "user"])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--user-id", type=UUID)
    parser.add_argument("--plan", type=Plan)
    parser.add_argument("--exhausted", action="store_true")
    parser.add_argument("--due-sense", type=int)
    arguments = parser.parse_args()
    try:
        if arguments.operation == "baseline":
            asyncio.run(baseline(arguments.manifest))
        else:
            if arguments.user_id is None:
                parser.error("user preparation requires --user-id")
            asyncio.run(
                user_state(
                    arguments.user_id,
                    arguments.plan,
                    arguments.exhausted,
                    arguments.due_sense,
                )
            )
    except Exception as error:
        if arguments.manifest is not None:
            arguments.manifest.with_name("seed-failure.json").write_text(
                json.dumps({"error_type": type(error).__name__})
            )
        raise
