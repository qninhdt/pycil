"""Content DTOs. Sense content fields are populated from LexiClient responses,
never from pycil rows (pycil stores only opaque ``senseId`` membership)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WordRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)


class GenerationCreateRead(BaseModel):
    """The receipt for an accepted word generation: the task to subscribe to."""

    model_config = ConfigDict(populate_by_name=True)

    task_id: UUID = Field(serialization_alias="taskId")


class SenseContent(BaseModel):
    sense_id: int | None = Field(default=None, serialization_alias="senseId")
    definition: str
    tier: str
    pos: str | None = None
    cefr_level: str | None = Field(default=None, serialization_alias="cefrLevel")
    examples: list[str] = Field(default_factory=list)
    # The headword. Without it a listing renders definitions with nothing to label
    # them. Deliberately the ONLY addition to this DTO: it is also produced inside
    # the per-result loop in ``search_words``, so anything else added here is paid
    # for on every keystroke by a UI that does not render it. The full lexical
    # record lives on ``SenseDetailRead`` instead.
    word: str | None = None
    word_id: int | None = Field(default=None, serialization_alias="wordId")
    # Per-caller learning state, joined in one query for the whole deck. All None
    # for an anonymous caller and for a sense the caller has never studied, which
    # the UI renders as "not started" rather than as zero progress.
    #
    # Exception to the keep-it-lean rule above, and safe: these are populated only
    # by ``deck_items``. ``search_words`` leaves them None, so its payload is
    # unchanged and no extra query is added to the keystroke path.
    mastery: int | None = None
    mastery_stage: int | None = Field(default=None, serialization_alias="masteryStage")
    mastery_stage_name: str | None = Field(default=None, serialization_alias="masteryStageName")
    next_review_date: datetime | None = Field(default=None, serialization_alias="nextReviewDate")
    review_count: int | None = Field(default=None, serialization_alias="reviewCount")
    lapse_count: int | None = Field(default=None, serialization_alias="lapseCount")
    status: str | None = None


class SenseFormRead(BaseModel):
    """One inflected form: ``surface`` (ran) tagged with its ``inf`` label (past).

    Field names mirror Lexi's ``FormView`` exactly. Do not rename them to anything
    resembling an answer-key shape: ``test_v1_contract`` substring-scans the whole
    component-schema document for the three answer-safety tokens, so even prose in
    a docstring here can trip it.
    """

    inf: str
    surface: str


class SenseReferenceRead(BaseModel):
    source: str
    source_ref: str = Field(serialization_alias="sourceRef")


class SenseRelationRead(BaseModel):
    """A sense-level semantic relation. ``wsdState`` is derived by Lexi, not
    stored: ``resolved`` carries a target sense, ``pending`` and ``unresolvable``
    carry only the target word."""

    rel_type: str = Field(serialization_alias="relType")
    to_word_display: str = Field(serialization_alias="toWordDisplay")
    to_word_id: int = Field(serialization_alias="toWordId")
    to_word_status: str = Field(serialization_alias="toWordStatus")
    wsd_state: str = Field(serialization_alias="wsdState")
    to_sense_id: int | None = Field(default=None, serialization_alias="toSenseId")
    to_sense_gloss: str | None = Field(default=None, serialization_alias="toSenseGloss")


class SenseDetailRead(BaseModel):
    """The full lexical record for one sense, returned by the single-sense read
    alone. Listing endpoints return ``SenseContent`` so their payload does not
    grow."""

    sense_id: int = Field(serialization_alias="senseId")
    word: str | None = None
    word_id: int | None = Field(default=None, serialization_alias="wordId")
    definition: str
    tier: str
    pos: str | None = None
    cefr_level: str | None = Field(default=None, serialization_alias="cefrLevel")
    examples: list[str] = Field(default_factory=list)
    ipa_uk: str | None = Field(default=None, serialization_alias="ipaUk")
    ipa_us: str | None = Field(default=None, serialization_alias="ipaUs")
    guideword: str | None = None
    grammar: list[str] = Field(default_factory=list)
    register: str | None = None
    connotation: str | None = None
    collocations: list[str] = Field(default_factory=list)
    domain: str | None = None
    usage_note: str | None = Field(default=None, serialization_alias="usageNote")
    forms: list[SenseFormRead] = Field(default_factory=list)
    references: list[SenseReferenceRead] = Field(default_factory=list)
    relations: list[SenseRelationRead] = Field(default_factory=list)


class WordSearchRead(BaseModel):
    display: str
    entry_type: str | None = Field(default=None, serialization_alias="entryType")
    score: float = 0.0
    lexi_word_id: int | None = Field(default=None, serialization_alias="wordId")
    cambridge_id: int | None = Field(default=None, serialization_alias="cambridgeId")
    gloss: str | None = None
    pos: str | None = None
    senses: list[SenseContent] = Field(default_factory=list)


class SenseAddRequest(BaseModel):
    sense_id: int = Field(alias="senseId")

    model_config = {"populate_by_name": True}
