"""Session planning: candidate admission, difficulty sampling,
question preparation, and immutable LearningPlan creation.

All planning operations are pure or read-only, producing an immutable LearningPlan
that is handed to the client.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import cast
from uuid import UUID

from lexi_ai.contracts import (
    Flashcard,
    FreeText,
    PrepareDemand,
    PresentedQuestion,
    RenderKind,
    SingleChoice,
    TextSpan,
)
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.lexicon.contracts import LexiReader
from pycil.library.models import Node, NodeType
from pycil.library.scope import resolve_sense_ids
from pycil.platform.product_config import system_config
from pycil.study.engine.fsrs import elapsed_days, recall
from pycil.study.engine.policy import (
    ASSESSMENT_FLOOR,
    NEW_WORD_FLOOR,
    sample_requested_level,
)
from pycil.study.models import ReviewLog, SenseStatus, UserLearningSettings, UserSenseStats
from pycil.study.schemas import (
    LearningPlan,
    LearningPlanItem,
    QuestionGrading,
    QuestionOption,
    SessionQuestionRead,
)

_STATS_SQL = text(
    """
    SELECT sense_id, stability, difficulty, mastery, interval_days,
           last_review_date, next_review_date, review_count, lapse_count,
           status, depth_level, depth_streak, created_at, updated_at, user_id
    FROM user_sense_stats
    WHERE user_id = :user_id AND sense_id = ANY(CAST(:sense_ids AS bigint[]))
    """
)


@dataclass(frozen=True)
class DueCandidate:
    """A scheduled sense that is due for review, ranked for admission."""

    sense_id: int
    mastery: int
    depth_level: int
    recall: float
    overdue_seconds: float


@dataclass(frozen=True)
class AdmittedSense:
    sense_id: int
    purpose: str  # "due" | "new"
    requested_level: int


@dataclass(frozen=True)
class SessionSettings:
    target_words_per_session: int
    max_questions_per_round: int


@dataclass(frozen=True)
class PlanResult:
    admitted: list[AdmittedSense]
    demands: list[PrepareDemand]


@dataclass(frozen=True)
class ResolvedQuestion:
    question: PresentedQuestion
    requested_level: int
    served_level: int
    is_fallback: bool
    is_graded: bool = True


async def load_candidates(
    session: AsyncSession,
    user_id: UUID,
    node_id: UUID,
    now: datetime,
) -> tuple[list[DueCandidate], list[int]]:
    """Return due and new senses in the authorized node scope."""
    sense_ids = await resolve_sense_ids(session, node_id, viewer_id=user_id)
    if not sense_ids:
        return [], []

    rows = await session.execute(_STATS_SQL, {"user_id": str(user_id), "sense_ids": sense_ids})
    stats = {int(row.sense_id): UserSenseStats.model_validate(row._mapping) for row in rows}

    due: list[DueCandidate] = []
    new: list[int] = []
    for sense_id in sense_ids:
        state = stats.get(sense_id)
        if state is None or state.status == SenseStatus.new:
            new.append(sense_id)
        elif state.status == SenseStatus.scheduled:
            if state.next_review_date is not None and state.next_review_date <= now:
                recall_probability = recall(
                    state.stability, elapsed_days(state.last_review_date, now)
                )
                overdue = (now - state.next_review_date).total_seconds()
                due.append(
                    DueCandidate(
                        sense_id=sense_id,
                        mastery=state.mastery,
                        depth_level=state.depth_level,
                        recall=recall_probability,
                        overdue_seconds=overdue,
                    )
                )

    due.sort(key=lambda candidate: (candidate.recall, -candidate.overdue_seconds))
    return due, new


def default_session_settings() -> SessionSettings:
    """The product defaults for session shape, owned by ``config/config.yaml``."""
    learning = system_config.learning
    return SessionSettings(
        target_words_per_session=learning.max_words_per_session,
        max_questions_per_round=learning.max_questions_per_round,
    )


async def settings_for_user(session: AsyncSession, user_id: UUID) -> SessionSettings:
    """Read the learner's effective two-number session shape."""
    row = await session.get(UserLearningSettings, user_id)
    if row is None:
        return default_session_settings()
    return SessionSettings(
        target_words_per_session=max(1, row.target_words_per_session),
        max_questions_per_round=max(1, row.max_questions_per_round),
    )


async def save_settings(
    session: AsyncSession,
    user_id: UUID,
    *,
    target_words_per_session: int,
    max_questions_per_round: int,
    now: datetime | None = None,
) -> SessionSettings:
    """Persist the learner's two session-shape settings with an upsert."""
    moment = now if now is not None else datetime.now(UTC)
    statement = pg_insert(UserLearningSettings).values(
        user_id=user_id,
        target_words_per_session=target_words_per_session,
        max_questions_per_round=max_questions_per_round,
        updated_at=moment,
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "target_words_per_session": statement.excluded.target_words_per_session,
                "max_questions_per_round": statement.excluded.max_questions_per_round,
                "updated_at": statement.excluded.updated_at,
            },
        )
    )
    await session.commit()
    return SessionSettings(
        target_words_per_session=target_words_per_session,
        max_questions_per_round=max_questions_per_round,
    )


def _slot_split(target: int, due_available: int) -> tuple[int, int]:
    """Return ``(new_slots, due_slots)`` while reserving the new-word floor."""
    new_slots = min(max(NEW_WORD_FLOOR, target - due_available), target)
    return new_slots, target - new_slots


def _admit(
    due: list[DueCandidate],
    new: list[int],
    target: int,
    new_slots: int,
    due_slots: int,
) -> tuple[list[DueCandidate], list[int]]:
    """Admit due-first up to slots, then backfill any shortfall."""
    due_take = min(due_slots, len(due))
    new_take = min(new_slots, len(new))
    capacity = target - due_take - new_take
    extra_due = min(capacity, len(due) - due_take)
    due_take += extra_due
    capacity -= extra_due
    new_take += min(capacity, len(new) - new_take)
    return due[:due_take], new[:new_take]


def _requirements(
    admitted_due: list[DueCandidate],
    admitted_new: list[int],
    rng: random.Random,
) -> list[AdmittedSense]:
    """Build exactly one assessment requirement per admitted sense."""
    admitted = [
        AdmittedSense(
            sense_id=candidate.sense_id,
            purpose="due",
            requested_level=sample_requested_level(candidate.depth_level, rng),
        )
        for candidate in admitted_due
    ]
    admitted.extend(
        AdmittedSense(sense_id=sense_id, purpose="new", requested_level=ASSESSMENT_FLOOR)
        for sense_id in admitted_new
    )
    return admitted


def _demands(admitted: list[AdmittedSense]) -> list[PrepareDemand]:
    """Request one library item for each admitted sense and sampled level."""
    return [
        PrepareDemand(sense_id=item.sense_id, difficulty_level=item.requested_level)
        for item in admitted
    ]


async def plan_session(
    session: AsyncSession,
    user_id: UUID,
    node_id: UUID,
    now: datetime,
    settings: SessionSettings,
    rng: random.Random | None = None,
) -> PlanResult:
    """Select senses once and build one graded demand for each."""
    picker = rng if rng is not None else random.Random()
    due, new = await load_candidates(session, user_id, node_id, now)
    target = settings.target_words_per_session
    new_slots, due_slots = _slot_split(target, len(due))
    admitted_due, admitted_new = _admit(due, new, target, new_slots, due_slots)
    admitted = _requirements(admitted_due, admitted_new, picker)
    return PlanResult(admitted=admitted, demands=_demands(admitted))


def _assessment_type_ids(reader: LexiReader, level: int) -> list[str]:
    return [
        info.type_id
        for info in reader.question_types()
        if level in info.difficulty_levels and info.interaction == "assessment"
    ]


async def resolve_question(
    reader: LexiReader,
    sense_id: int,
    requested_level: int,
    excluded_ids: frozenset[int],
    rng: random.Random | None = None,
) -> ResolvedQuestion | None:
    """Resolve the highest matching difficulty question for an admitted sense."""
    picker = rng if rng is not None else random.Random()
    for level in range(requested_level, 0, -1):
        type_ids = _assessment_type_ids(reader, level)
        picker.shuffle(type_ids)
        for type_id in type_ids:
            question = await reader.retrieve_question(sense_id, level, excluded_ids, type_id)
            if question is not None:
                return ResolvedQuestion(
                    question=question,
                    requested_level=requested_level,
                    served_level=level,
                    is_fallback=level < requested_level,
                    is_graded=True,
                )
    return None


async def resolve_exposure(reader: LexiReader, sense_id: int) -> ResolvedQuestion:
    """Resolve an exposure card."""
    question = await reader.retrieve_exposure(sense_id)
    return ResolvedQuestion(
        question=question,
        requested_level=0,
        served_level=0,
        is_fallback=False,
        is_graded=False,
    )


def extract_presentation(
    question: PresentedQuestion,
) -> tuple[str | None, list[QuestionOption] | None, dict]:
    """Map a question to presentation stem/prompt, options list, and raw payload."""
    render_kind = question.render_kind
    if render_kind is RenderKind.SINGLE_CHOICE:
        render = cast(SingleChoice, question.render)
        letters = ["a", "b", "c", "d", "e", "f", "g", "h"]
        options = [
            QuestionOption(
                id=letters[i] if i < len(letters) else str(i),
                text=opt,
            )
            for i, opt in enumerate(render.options)
        ]
        return render.stem, options, {"stem": render.stem, "options": list(render.options)}

    if render_kind is RenderKind.TEXT_SPAN:
        render = cast(TextSpan, question.render)
        return (
            render.stem_with_blank,
            None,
            {
                "stem_with_blank": render.stem_with_blank,
                "word_bank": list(render.word_bank),
            },
        )

    if render_kind is RenderKind.FREE_TEXT:
        render = cast(FreeText, question.render)
        return render.prompt, None, {"prompt": render.prompt}

    if render_kind is RenderKind.FLASHCARD:
        render = cast(Flashcard, question.render)
        return (
            render.word,
            None,
            {
                "word": render.word,
                "definition": render.definition,
                "pos": render.pos,
                "example": render.example,
                "ipa_uk": render.ipa_uk,
                "ipa_us": render.ipa_us,
            },
        )

    return None, None, {}


async def extract_grading_spec(reader: LexiReader, question: PresentedQuestion) -> QuestionGrading:
    """Determine client or server grading configuration."""
    format_name = question.render_kind.value
    if format_name == "free_text":
        return QuestionGrading(mode="server")

    letters = ["a", "b", "c", "d", "e", "f", "g", "h"]

    if format_name == "single_choice":
        correct_idx: int | None = None
        correct_opt: str | None = None
        correct_opt_id: str | None = None

        if hasattr(reader, "_questions"):
            repo = getattr(reader._questions, "_repository", None)
            if repo is not None and hasattr(repo, "get"):
                pq = await repo.get(question.question_id)
                if pq is not None and "correct_index" in pq.payload:
                    correct_idx = pq.payload["correct_index"]
                    opts = pq.payload.get("options", [])
                    if 0 <= correct_idx < len(opts):
                        correct_opt = opts[correct_idx]
                        correct_opt_id = (
                            letters[correct_idx] if correct_idx < len(letters) else str(correct_idx)
                        )

        if correct_opt is None and hasattr(reader, "_answers"):
            ans = reader._answers.get(question.question_id)
            if ans is not None:
                correct_opt = str(ans)
                if hasattr(question.render, "options"):
                    for idx, o in enumerate(question.render.options):
                        if o == correct_opt:
                            correct_idx = idx
                            correct_opt_id = letters[idx] if idx < len(letters) else str(idx)
                            break
                if correct_opt_id is None:
                    correct_opt_id = "a"

        return QuestionGrading(
            mode="client",
            correct_index=correct_idx,
            correct_option=correct_opt,
            correct_option_id=correct_opt_id,
            answer=correct_opt,
        )

    if format_name == "text_span":
        norm: str | None = None
        accepted: list[str] = []
        if hasattr(reader, "_questions"):
            repo = getattr(reader._questions, "_repository", None)
            if repo is not None and hasattr(repo, "get"):
                pq = await repo.get(question.question_id)
                if pq is not None:
                    norm = pq.payload.get("answer_norm")
                    accepted = list(pq.payload.get("accepted_forms", []))
        if norm is None and hasattr(reader, "_answers"):
            norm = reader._answers.get(question.question_id, "run")
            accepted = [norm]
        return QuestionGrading(
            mode="client",
            answer_norm=norm,
            accepted_forms=accepted,
            answer=norm,
        )

    return QuestionGrading(mode="client")


async def create_session_learning_plan(
    session: AsyncSession,
    reader: LexiReader,
    user_id: UUID,
    node_id: UUID,
    now: datetime,
    settings: SessionSettings,
    rng: random.Random | None = None,
) -> tuple[LearningPlan, list[SessionQuestionRead]]:
    """Build the complete, immutable LearningPlan and client question representations."""
    plan_res = await plan_session(session, user_id, node_id, now, settings, rng)
    plan_items: list[LearningPlanItem] = []
    questions: list[SessionQuestionRead] = []
    excluded_ids: set[int] = set()

    for admitted in plan_res.admitted:
        resolved = await resolve_question(
            reader,
            admitted.sense_id,
            admitted.requested_level,
            frozenset(excluded_ids),
            rng=rng,
        )
        if resolved is None:
            # Fallback to any available assessment question for this sense
            sense_questions = await reader.list_questions_for_sense(admitted.sense_id)
            assessments = [
                q
                for q in sense_questions
                if q.interaction == "assessment" and q.question_id not in excluded_ids
            ]
            if assessments:
                chosen = assessments[0]
                resolved = ResolvedQuestion(
                    question=chosen,
                    requested_level=admitted.requested_level,
                    served_level=chosen.difficulty_level,
                    is_fallback=chosen.difficulty_level != admitted.requested_level,
                    is_graded=True,
                )
            elif admitted.purpose == "new":
                resolved = await resolve_exposure(reader, admitted.sense_id)

        if resolved is None:
            continue

        q = resolved.question
        if q.question_id is None:
            continue

        excluded_ids.add(q.question_id)
        format_name = q.render_kind.value
        grading_mode = "server" if format_name == "free_text" else "client"

        plan_items.append(
            LearningPlanItem(
                question_id=q.question_id,
                sense_id=admitted.sense_id,
                purpose="due" if admitted.purpose == "due" else "new",
                requested_level=admitted.requested_level,
                served_level=resolved.served_level,
                grading_mode=grading_mode,
            )
        )

        prompt, options, payload = extract_presentation(q)
        grading_spec = await extract_grading_spec(reader, q)

        questions.append(
            SessionQuestionRead(
                id=q.question_id,
                sense_id=admitted.sense_id,
                format=format_name,
                prompt=prompt,
                options=options,
                payload=payload,
                grading=grading_spec,
            )
        )

    learning_plan = LearningPlan(version=1, items=plan_items)
    return learning_plan, questions


# --- Dashboard read model ----------------------------------------------------

FORECAST_DAYS = 7


@dataclass(frozen=True)
class ForecastDay:
    day: date
    due_count: int


@dataclass(frozen=True)
class ResumeTarget:
    """Which deck "continue where you left off" should open."""

    node_id: UUID
    deck_title: str
    remaining_count: int


@dataclass(frozen=True)
class DashboardStats:
    total_learned_words: int
    due_today_count: int
    mastery_percentage: float
    forecast: list[ForecastDay]
    resume: ResumeTarget | None


def _engaged():
    """The durable learning boundary: FSRS has scheduled the sense."""
    return UserSenseStats.status == SenseStatus.scheduled


async def load_dashboard(session: AsyncSession, user_id: UUID, now: datetime) -> DashboardStats:
    """Every figure the dashboard shows, for one learner."""
    engaged = _engaged()

    total_learned = (
        await session.execute(
            select(func.count(UserSenseStats.sense_id)).where(
                UserSenseStats.user_id == user_id, engaged
            )
        )
    ).scalar() or 0

    due_today = (
        await session.execute(
            select(func.count(UserSenseStats.sense_id)).where(
                UserSenseStats.user_id == user_id,
                UserSenseStats.status == SenseStatus.scheduled,
                UserSenseStats.next_review_date <= now,
            )
        )
    ).scalar() or 0

    average = (
        await session.execute(
            select(func.avg(UserSenseStats.mastery)).where(
                UserSenseStats.user_id == user_id, engaged
            )
        )
    ).scalar()

    return DashboardStats(
        total_learned_words=int(total_learned),
        due_today_count=int(due_today),
        mastery_percentage=round(float(average), 1) if average is not None else 0.0,
        forecast=await _forecast(session, user_id, now),
        resume=await _resume_target(session, user_id, now, due_today=int(due_today)),
    )


async def _forecast(session: AsyncSession, user_id: UUID, now: datetime) -> list[ForecastDay]:
    """Due counts for the next `FORECAST_DAYS` days, overdue folded into today."""
    today = now.date()
    counts: dict[date, int] = {today + timedelta(days=i): 0 for i in range(FORECAST_DAYS)}
    horizon = now + timedelta(days=FORECAST_DAYS)

    due_dates = await session.scalars(
        select(UserSenseStats.next_review_date).where(
            UserSenseStats.user_id == user_id,
            UserSenseStats.next_review_date.is_not(None),
            UserSenseStats.next_review_date < horizon,
        )
    )
    for next_review in due_dates:
        if next_review is None:
            continue
        day = next_review.date()
        if day <= today:
            counts[today] += 1
        elif day in counts:
            counts[day] += 1

    return [ForecastDay(day=day, due_count=count) for day, count in sorted(counts.items())]


async def _resume_target(
    session: AsyncSession, user_id: UUID, now: datetime, *, due_today: int
) -> ResumeTarget | None:
    """The deck the learner last reviewed in, or their first deck as a fallback."""
    recent_node_id = (
        await session.execute(
            select(ReviewLog.node_id)
            .where(ReviewLog.user_id == user_id, ReviewLog.node_id.is_not(None))
            .order_by(ReviewLog.reviewed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if recent_node_id is not None:
        node = await session.get(Node, recent_node_id)
        if node is not None:
            return ResumeTarget(node_id=node.id, deck_title=node.name, remaining_count=due_today)

    first_deck = (
        await session.scalars(
            select(Node)
            .where(Node.author_id == user_id, Node.type == NodeType.DECK)
            .order_by(Node.created_at, Node.id)
            .limit(1)
        )
    ).first()
    if first_deck is None:
        return None
    return ResumeTarget(
        node_id=first_deck.id,
        deck_title=first_deck.name,
        remaining_count=due_today,
    )
