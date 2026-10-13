from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pycil.library.models import NodeRole, NodeSpace, NodeType
from pycil.study.enums import LearningState
from pycil.study.schemas import Summary
from pycil.vocabulary.enums import CEFRLevel, EntryType, PartOfSpeech, Register, Tier
from pycil.vocabulary.schemas import Example


class SenseSort(StrEnum):
    SENSE_ID_ASC = "sense_id_asc"
    LEMMA_ASC = "lemma_asc"
    LAST_REVIEWED_DESC = "last_reviewed_desc"
    MASTERY_ASC = "mastery_asc"


class LibraryView(StrEnum):
    CONTENT = "content"
    STRUCTURE = "structure"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NodeCreate(Strict):
    type: NodeType
    reference_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    parent_id: UUID | None = None
    confirm_publication: bool = False
    sense_ids: list[Annotated[int, Field(strict=True, gt=0)]] | None = None

    @model_validator(mode="after")
    def editable_values(self):
        if not self.name.strip():
            raise ValueError("blank node name")
        if self.sense_ids is not None and len(set(self.sense_ids)) != len(self.sense_ids):
            raise ValueError("Sense IDs must be unique")
        if (self.type is NodeType.REFERENCE) != (self.reference_id is not None):
            raise ValueError("reference shape invalid")
        if self.type is not NodeType.DECK and self.sense_ids is not None:
            raise ValueError("membership is deck-only")
        return self


class NodePatch(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)

    @model_validator(mode="after")
    def supplied_fields(self):
        if not self.model_fields_set or (
            "name" in self.model_fields_set and (self.name is None or not self.name.strip())
        ):
            raise ValueError("Supply a nonblank name or description")
        return self


class SenseDelta(Strict):
    add: list[Annotated[int, Field(strict=True, gt=0)]] = Field(
        default_factory=lambda: [], max_length=1000
    )
    remove: list[Annotated[int, Field(strict=True, gt=0)]] = Field(
        default_factory=lambda: [], max_length=1000
    )

    @model_validator(mode="after")
    def distinct_ids(self) -> Self:
        if len(set(self.add)) != len(self.add) or len(set(self.remove)) != len(self.remove):
            raise ValueError("Sense IDs must be unique")
        if set(self.add) & set(self.remove):
            raise ValueError("A sense cannot be added and removed together")
        return self


class NodeDestination(Strict):
    parent_id: UUID
    confirm_publication: bool = False


class NodeMove(NodeDestination):
    retain_personal_reference: bool = False


class LearningPreview(Strict):
    state: Literal[LearningState.NEW, LearningState.DUE, LearningState.NOT_YET_DUE]
    due_at: datetime | None
    elo: float | None
    level: Annotated[int, Field(ge=1, le=5)] | None
    last_reviewed_at: datetime | None


class SourceDeck(Strict):
    id: UUID
    name: str
    owner_id: UUID
    space: NodeSpace
    editable: bool


class Sources(Strict):
    decks: list[SourceDeck]
    next_cursor: str | None


class SensePreview(Strict):
    sense_id: int
    word_id: int
    lemma: str
    entry_type: EntryType | None
    pos: PartOfSpeech
    tier: Tier
    definition: str | None
    cefr_level: CEFRLevel | None
    register_: Register | None = Field(alias="register")
    ipa_uk: str | None
    ipa_us: str | None
    learning: LearningPreview | None
    examples: list[Example] | None = None
    sources: list[SourceDeck] | None = None
    source_count: int | None = None
    sources_has_more: bool | None = None


class SensePage(Strict):
    senses: list[SensePreview]
    next_cursor: str | None
    as_of: datetime


class NodeView[T: NodeType = NodeType](Strict):
    id: UUID
    owner_id: UUID
    type: T
    parent_id: UUID | None
    reference_id: UUID | None
    name: str
    description: str | None
    role: NodeRole
    space: NodeSpace
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    summary: Summary | None = None


class NodePage(Strict):
    nodes: list[NodeView]
    next_cursor: str | None


class NodeViewWithReference(NodeView):
    retained_reference_id: UUID | None = None


class ContainerNode(NodeView[Literal[NodeType.FOLDER, NodeType.REFERENCE]]):
    pass


class SavedDeck(NodeView[Literal[NodeType.DECK]]):
    sense_ids: list[int]
    retained_reference_id: UUID | None = None


class SavedContainer(ContainerNode):
    retained_reference_id: UUID | None = None


SavedNode = Annotated[SavedDeck | SavedContainer, Field(discriminator="type")]


class Breadcrumb(Strict):
    id: UUID
    name: str


class NodeDetails(NodeView):
    breadcrumbs: list[Breadcrumb]
    reference_available: bool | None = None
