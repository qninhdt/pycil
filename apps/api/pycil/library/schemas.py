from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from lexi_ai import CEFRLevel, EntryType, PartOfSpeech, Register, Tier
from pydantic import BaseModel, ConfigDict, Field, model_validator

from pycil.library.models import NodeType, Visibility
from pycil.study.models import Rating


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EditableNode(Strict):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    parent_id: UUID | None = None
    visibility: Visibility = Visibility.PRIVATE
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
    visibility: Visibility


class DeckSnapshot(Strict):
    id: UUID
    owner_id: UUID
    type: Literal["DECK"]
    name: str
    description: str | None
    parent_id: UUID | None
    visibility: Visibility
    created_at: datetime
    updated_at: datetime
    sense_ids: list[int]


class LearningPreview(Strict):
    state: Literal["NEW", "DUE", "NOT_YET_DUE"]
    mastery: int = Field(ge=0, le=100)
    due_at: datetime | None
    last_rating: Rating | None


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


class DeckSenses(Strict):
    senses: list[SensePreview]


class SensePage(DeckSenses):
    next_after_id: int | None


class NodeView(Strict):
    id: UUID
    owner_id: UUID
    type: NodeType
    parent_id: UUID | None
    reference_id: UUID | None
    name: str
    description: str | None
    visibility: Visibility
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class NodePage(Strict):
    nodes: list[NodeView]
    next_after_id: UUID | None


class ContainerNode(NodeView):
    type: Literal[NodeType.FOLDER, NodeType.REFERENCE]


class SavedDeck(NodeView):
    type: Literal[NodeType.DECK]
    sense_ids: list[int]


SavedNode = Annotated[SavedDeck | ContainerNode, Field(discriminator="type")]


class Breadcrumb(Strict):
    id: UUID
    name: str


class ContainerDetails(ContainerNode):
    breadcrumbs: list[Breadcrumb]
    sense_count: int


class DeckDetails(NodeView):
    type: Literal[NodeType.DECK]
    breadcrumbs: list[Breadcrumb]
    sense_count: int
    senses: list[SensePreview]


NodeDetails = Annotated[DeckDetails | ContainerDetails, Field(discriminator="type")]
