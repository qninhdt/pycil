from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header
from lexi_ai import ResponseFormat
from lexi_ai.errors import LexiconError, QuestionNotFoundError, UnsupportedQuestionFormatError
from sqlalchemy import select

from pycil.account.auth import Actor
from pycil.account.models import User
from pycil.account.plans import Feature
from pycil.dependencies import Dictionary, Product, Session
from pycil.http import Problem
from pycil.study.preparation import prepare
from pycil.study.progress import history, progress
from pycil.study.reviews import review
from pycil.study.schemas import (
    Grade,
    GradeResult,
    History,
    Preparation,
    Prepare,
    Progress,
    Review,
    ReviewResult,
)

router = APIRouter(prefix="/v1/study", tags=["study"])


@router.post("/prepare", response_model=Preparation)
async def preparation(
    data: Prepare, user: Actor, session: Session, config: Product, lexicon: Dictionary
):
    return await prepare(session, lexicon, user, data.node_id, config)


@router.post("/grade", response_model=GradeResult)
async def grade(data: Grade, user: Actor, config: Product, lexicon: Dictionary, session: Session):
    async with session.begin():
        plan = await session.scalar(select(User.plan).where(User.id == user.id))
    if plan is None:
        raise Problem(404, "account_not_found")
    if Feature.ADVANCED_GRADING not in config.plans[plan].features:
        raise Problem(403, "advanced_grading_not_available")
    if (
        data.format is ResponseFormat.SINGLE_CHOICE
        or not data.answer.strip()
        or len(data.answer) > config.learning.limits.max_answer_chars
    ):
        raise Problem(422, "invalid_grade_request")
    try:
        return await lexicon.grade_answer(
            data.question_id,
            data.format,
            data.answer,
            mode=config.providers.lexi.decision_mode,
            allowed_pairs={
                (kind, fmt)
                for kind, formats in config.learning.pair_levels.items()
                for fmt in formats
            },
        )
    except QuestionNotFoundError:
        raise Problem(404, "question_not_found") from None
    except UnsupportedQuestionFormatError:
        raise Problem(422, "unsupported_question_format") from None
    except LexiconError:
        raise Problem(503, "grading_unavailable") from None


@router.post("/reviews", response_model=ReviewResult)
async def rating(
    data: Review,
    user: Actor,
    session: Session,
    config: Product,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    return await review(session, user.id, data, idempotency_key, config)


@router.get("/progress", response_model=Progress)
async def summary(user: Actor, session: Session, config: Product, node_id: UUID | None = None):
    return await progress(session, user, config, node_id)


@router.get("/history", response_model=History)
async def events(
    user: Actor, session: Session, config: Product, days: int = 30, after: UUID | None = None
):
    return await history(session, user, config, days, after)
