"""Bounded task inputs, independent of HTTP response shapes."""

from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from ag_ui.core import Message
from pydantic import Field, JsonValue, StringConstraints, model_validator

from pycil.library.models import NodeSpace, NodeType
from pycil.library.schemas import LibraryView, SenseDelta, SenseSort, Strict
from pycil.study.enums import LearningState

PositiveID = Annotated[int, Field(strict=True, gt=0)]
Query = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Queries = Annotated[list[Query], Field(min_length=1, max_length=10)]
VocabularyInclude = Literal["examples", "lexical_details", "learning", "sources"]


class CurrentView(Strict):
    path: str = Field(min_length=1, max_length=512, pattern=r"^/")
    node_id: UUID | None = None
    word_id: PositiveID | None = None

    @model_validator(mode="after")
    def one_target(self) -> Self:
        if self.node_id is not None and self.word_id is not None:
            raise ValueError("Supply a node or a Word, not both")
        return self


class WordSearch(Strict):
    queries: Queries
    limit: Annotated[int, Field(strict=True, ge=1, le=10)] = 3
    include: list[VocabularyInclude] = Field(default_factory=list[VocabularyInclude])


class WordGeneration(Strict):
    reference_ids: list[Annotated[str, StringConstraints(min_length=1, max_length=64)]] = Field(
        min_length=1, max_length=10
    )


class VocabularyRead(Strict):
    word_ids: list[PositiveID] = Field(default_factory=list[PositiveID], max_length=30)
    sense_ids: list[PositiveID] = Field(default_factory=list[PositiveID], max_length=100)
    include: list[VocabularyInclude] = Field(default_factory=list[VocabularyInclude])

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if not self.word_ids and not self.sense_ids:
            raise ValueError("Supply Word or sense IDs")
        return self


class NodeSearch(Strict):
    queries: Queries
    scope: Literal[NodeSpace.LIBRARY, NodeSpace.PUBLISHED] = NodeSpace.LIBRARY
    node_id: UUID | None = None
    type: Literal[NodeType.DECK, NodeType.FOLDER, NodeType.REFERENCE] | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=10)] = 3

    @model_validator(mode="after")
    def scope_shape(self):
        if self.scope == NodeSpace.PUBLISHED and self.node_id is not None:
            raise ValueError("Use LIBRARY for a specific readable node")
        return self


class LibraryRead(Strict):
    node_id: UUID | None = None
    view: Literal[LibraryView.CONTENT, LibraryView.STRUCTURE] = LibraryView.CONTENT
    query: Query | None = None
    state: Literal[
        LearningState.ALL, LearningState.NEW, LearningState.DUE, LearningState.NOT_YET_DUE
    ] = LearningState.ALL
    sort: Literal[
        SenseSort.SENSE_ID_ASC,
        SenseSort.LEMMA_ASC,
        SenseSort.LAST_REVIEWED_DESC,
        SenseSort.MASTERY_ASC,
    ] = SenseSort.SENSE_ID_ASC
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 20
    cursor: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def structure_filters(self):
        if self.view == LibraryView.STRUCTURE and (
            self.query is not None
            or self.state != LearningState.ALL
            or self.sort != SenseSort.SENSE_ID_ASC
        ):
            raise ValueError("Content filters require CONTENT view")
        return self


class NodeUpdate(Strict):
    node_id: UUID
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    clear_description: bool = False
    add_sense_ids: list[PositiveID] = Field(default_factory=list[PositiveID], max_length=1000)
    remove_sense_ids: list[PositiveID] = Field(default_factory=list[PositiveID], max_length=1000)

    @model_validator(mode="after")
    def update_shape(self) -> Self:
        if self.name is not None and not self.name.strip():
            raise ValueError("name must not be blank")
        if self.clear_description and self.description is not None:
            raise ValueError("Supply description or clear_description, not both")
        if (
            self.name is None
            and self.description is None
            and not self.clear_description
            and not (self.add_sense_ids or self.remove_sense_ids)
        ):
            raise ValueError("Supply metadata or a membership change")
        SenseDelta(add=self.add_sense_ids, remove=self.remove_sense_ids)
        return self


class NodeBatch(Strict):
    node_ids: list[UUID] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.node_ids)) != len(self.node_ids):
            raise ValueError("Duplicate node IDs")
        return self


class NodeCopy(NodeBatch):
    parent_id: UUID
    confirm_publication: bool = False


class NodeMove(NodeCopy):
    retain_personal_reference: bool = False


class DateWindow(Strict):
    start_date: date
    end_date: date


class LearningOverview(Strict):
    node_ids: list[UUID] = Field(default_factory=list[UUID], max_length=20)
    include: list[Literal["activity", "schedule"]] = Field(
        default_factory=list[Literal["activity", "schedule"]]
    )
    activity_window: DateWindow | None = None
    schedule_window: DateWindow | None = None

    @model_validator(mode="after")
    def requested_windows(self) -> Self:
        if self.activity_window is not None and "activity" not in self.include:
            raise ValueError("Activity window requires activity")
        if self.schedule_window is not None and "schedule" not in self.include:
            raise ValueError("Schedule window requires schedule")
        return self


class CreateConversation(Strict):
    title: str | None = Field(default=None, max_length=255)


class AssistantModel(Strict):
    id: str
    name: str
    vision: bool
    efforts: list[str]


class ConversationView(Strict):
    id: UUID
    user_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationPage(Strict):
    conversations: list[ConversationView]
    next_cursor: str | None


class ApprovalAction(Strict):
    name: str
    args: dict[str, JsonValue]
    description: str | None = None


class ApprovalConfig(Strict):
    action_name: str
    allowed_decisions: list[Literal["approve", "reject"]]


class PendingApproval(Strict):
    interrupt_id: str
    action_requests: list[ApprovalAction]
    review_configs: list[ApprovalConfig]


class ConversationState(Strict):
    messages: list[Message]
    pending_approvals: list[PendingApproval]


class ConversationDetails(ConversationView):
    state: ConversationState
