from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request
from lexi_ai import ResponseFormat
from lexi_ai.errors import LexiconError, QuestionNotFoundError, UnsupportedQuestionFormatError
from sqlalchemy import select

from pycil.account.auth import Actor, Viewer
from pycil.account.models import User
from pycil.account.plans import Feature
from pycil.dependencies import Dictionary, Product, Session
from pycil.http import Problem
from pycil.pagination import strict_query
from pycil.study.preparation import prepare
from pycil.study.progress import activity, progress, schedule, summaries
from pycil.study.reviews import review
from pycil.study.schemas import (
    Activity,
    BatchResult,
    Grade,
    GradeResult,
    Preparation,
    Prepare,
    ReviewBatch,
    Schedule,
    Summary,
    SummaryBatch,
)

router = APIRouter(prefix="/v1/study", tags=["study"])


@router.post("/prepare", response_model=Preparation)
async def preparation(
    data: Prepare, user: Actor, session: Session, config: Product, lexicon: Dictionary
):
    return await prepare(
        session,
        lexicon,
        user,
        data.node_id,
        config,
        selection=data.selection,
        max_sense_count=data.max_sense_count,
    )


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


@router.post("/reviews", response_model=BatchResult)
async def rating(
    data: ReviewBatch,
    user: Actor,
    session: Session,
    config: Product,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    return await review(session, user.id, data, idempotency_key, config)


@router.get("/progress", response_model=Summary)
async def summary(
    request: Request, user: Actor, session: Session, config: Product, node_id: UUID | None = None
):
    strict_query(request, {"node_id"})
    return await progress(session, user, config, node_id)


@router.post("/summaries", response_model=list[Summary], openapi_extra={"security": [{}]})
async def cards(data: SummaryBatch, viewer: Viewer, session: Session, config: Product):
    return await summaries(session, viewer.id if viewer else None, config, data.node_ids)


@router.get("/activity", response_model=Activity)
async def days(
    request: Request,
    user: Actor,
    session: Session,
    config: Product,
    start_date: date | None = None,
    end_date: date | None = None,
):
    strict_query(request, {"start_date", "end_date"})
    return await activity(session, user.id, config, start_date, end_date)


@router.get("/review-schedule", response_model=Schedule)
async def upcoming(
    request: Request,
    user: Actor,
    session: Session,
    config: Product,
    node_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
    strict_query(request, {"node_id", "start_date", "end_date"})
    return await schedule(session, user.id, config, node_id, start_date, end_date)
