from collections.abc import Mapping
from datetime import date
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Header, Request, Response
from openai import APIError
from sqlalchemy import select

from pycil.account.models import User
from pycil.account.plans import Feature
from pycil.app.auth import UserId, Viewer
from pycil.app.dependencies import Config, Runtime, Session
from pycil.app.http import Problem
from pycil.app.pagination import strict_query
from pycil.infrastructure.retry import ProviderOutputError
from pycil.jobs.schemas import Accepted
from pycil.observability import get_logger
from pycil.study.enums import ResponseFormat
from pycil.study.errors import QuestionArtifactNotFoundError, UnsupportedQuestionFormatError
from pycil.study.grading import grade_answer
from pycil.study.progress import activity, schedule, summaries
from pycil.study.reviews import review
from pycil.study.schemas import (
    Activity,
    BatchResult,
    Grade,
    GradeResult,
    Prepare,
    ReviewBatch,
    Schedule,
    Summary,
    SummaryBatch,
)
from pycil.study.tasks import request_preparation
from pycil.study.types import SummaryDict
from pycil.vocabulary.errors import VocabularyError

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/study", tags=["study"])


@router.post(":prepare", response_model=Accepted, status_code=202)
async def preparation(
    data: Prepare,
    user: UserId,
    config: Config,
    resources: Runtime,
    response: Response,
) -> Accepted:
    accepted = await request_preparation(
        resources.sessions,
        resources.redis,
        resources.broker,
        config.study,
        config.jobs,
        user,
        data,
        plans=config.account.plans,
    )
    response.headers.update({"Location": accepted.status_url, "Retry-After": "2"})
    return accepted


@router.post(":grade", response_model=GradeResult)
async def grade(
    data: Grade, user: UserId, config: Config, resources: Runtime, session: Session
) -> Mapping[str, object]:
    async with session.begin():
        plan = await session.scalar(select(User.plan).where(User.id == user))
    if plan is None:
        raise Problem(404, "account_not_found")
    if Feature.ADVANCED_GRADING not in config.account.plans[plan].features:
        raise Problem(403, "advanced_grading_not_available")
    if (
        data.format is ResponseFormat.SINGLE_CHOICE
        or data.answer is not None
        and (not data.answer.strip() or len(data.answer) > config.study.limits.max_answer_chars)
    ):
        raise Problem(422, "invalid_grade_request")
    try:
        diagnostics = await grade_answer(
            resources.sessions,
            resources.search,
            resources.decision_llm,
            resources.artifact_store,
            data.question_artifact_id,
            data.question_type,
            data.format,
            data.answer,
            policy=config.study.grading,
            allowed_pairs={
                (kind, fmt) for kind, formats in config.study.pair_levels.items() for fmt in formats
            },
        )
        return data.model_dump(exclude={"answer"}) | {
            "diagnostics": diagnostics.model_dump(mode="json")
        }
    except QuestionArtifactNotFoundError:
        raise Problem(404, "question_artifact_not_found") from None
    except UnsupportedQuestionFormatError:
        raise Problem(422, "unsupported_question_format") from None
    except VocabularyError, ProviderOutputError, APIError, httpx.HTTPError:
        logger.error(
            "study_grading_failed",
            user_id=str(user),
            question_artifact_id=data.question_artifact_id,
        )
        raise Problem(503, "grading_unavailable") from None


@router.post(":submitResults", response_model=BatchResult)
async def submit_results(
    data: ReviewBatch,
    user: UserId,
    session: Session,
    config: Config,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    return await review(
        session,
        user,
        data,
        idempotency_key,
        config.study,
        account_config=config.account,
    )


@router.get("/progress", response_model=Summary)
async def summary(
    request: Request, user: UserId, session: Session, config: Config, node_id: UUID | None = None
) -> SummaryDict:
    strict_query(request, {"node_id"})
    return (await summaries(session, user, config.study, [node_id], library_config=config.library))[
        0
    ]


@router.post(":batchSummarize", response_model=list[Summary], openapi_extra={"security": [{}]})
async def cards(
    data: SummaryBatch, viewer: Viewer, session: Session, config: Config
) -> list[SummaryDict]:
    return await summaries(
        session,
        viewer,
        config.study,
        data.node_ids,
        library_config=config.library,
    )


@router.get("/activity", response_model=Activity)
async def days(
    request: Request,
    user: UserId,
    session: Session,
    config: Config,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    strict_query(request, {"start_date", "end_date"})
    return await activity(
        session,
        user,
        config.study,
        start_date,
        end_date,
        account_config=config.account,
    )


@router.get("/review-schedule", response_model=Schedule)
async def upcoming(
    request: Request,
    user: UserId,
    session: Session,
    config: Config,
    node_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    strict_query(request, {"node_id", "start_date", "end_date"})
    return await schedule(
        session,
        user,
        config.study,
        node_id,
        start_date,
        end_date,
        account_config=config.account,
        library_config=config.library,
    )
