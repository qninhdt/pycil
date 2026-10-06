from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from lexi_ai import CEFRLevel, EntryType, PartOfSpeech, Register, Tier
from lexi_ai.models import Example
from pydantic import BaseModel, ConfigDict, Field, model_validator

from pycil.library.models import NodeRole, NodeSpace, NodeType
from pycil.study.models import Rating
from pycil.study.schemas import Summary


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EditableNode(Strict):
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
        return self


class NodeCreate(EditableNode):
    type: NodeType
    reference_id: UUID | None = None

    @model_validator(mode="after")
    def shape(self):
        if (self.type is NodeType.REFERENCE) != (self.reference_id is not None):
            raise ValueError("reference shape invalid")
        if self.type is not NodeType.DECK and self.sense_ids is not None:
            raise ValueError("membership is deck-only")
        return self


class NodeSave(EditableNode):
    retain_personal_reference: bool = False


class DeckSnapshot(Strict):
    id: UUID
    owner_id: UUID
    type: Literal["DECK"]
    name: str
    description: str | None
    parent_id: UUID | None
    role: NodeRole
    space: NodeSpace
    created_at: datetime
    updated_at: datetime
    sense_ids: list[int]


class LearningPreview(Strict):
    state: Literal["NEW", "DUE", "NOT_YET_DUE"]
    due_at: datetime | None
    last_rating: Rating | None
    last_reviewed_at: datetime | None


class SourceDeck(Strict):
    id: UUID
    name: str
    owner_id: UUID
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


class NodeView(Strict):
    id: UUID
    owner_id: UUID
    type: NodeType
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


class ContainerNode(NodeView):
    type: Literal[NodeType.FOLDER, NodeType.REFERENCE]


class SavedDeck(NodeView):
    type: Literal[NodeType.DECK]
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
