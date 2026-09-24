"""Assistant HTTP contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ThreadCreate(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=200)


class ModelPricingRead(BaseModel):
    """The tariffs a client may show, in USD per million tokens.

    Exposed so a selector can explain a relative cost without the client ever
    supplying a price: the server prices every call from its own catalog.
    """

    input_usd_per_m: float = Field(serialization_alias="inputUsdPerM")
    output_usd_per_m: float = Field(serialization_alias="outputUsdPerM")
    cached_read_usd_per_m: float = Field(serialization_alias="cachedReadUsdPerM")


class ModelRead(BaseModel):
    """One selectable model, with only the metadata a client needs.

    Credentials, provider routes and any internal field stay server-side; this is
    a projection of the enabled catalog, not the catalog itself.
    """

    id: str
    name: str
    provider: str
    vision: bool
    reasoning: bool
    supported_efforts: list[str] = Field(serialization_alias="supportedEfforts")
    context_window: int = Field(serialization_alias="contextWindow")
    max_output_tokens: int = Field(serialization_alias="maxOutputTokens")
    pricing: ModelPricingRead
    is_default: bool = Field(serialization_alias="isDefault")


class ModelCatalogRead(BaseModel):
    """The allowlist a client may choose from, plus the current default."""

    default_model: str = Field(serialization_alias="defaultModel")
    default_reasoning_effort: str = Field(serialization_alias="defaultReasoningEffort")
    models: list[ModelRead]

    @classmethod
    def from_config(cls) -> "ModelCatalogRead":
        """Project the enabled catalog into the client-safe shape.

        Only enabled models appear: a disabled entry is a considered model kept on
        record, and offering it would let a learner select something the gateway
        cannot run.
        """
        from pycil.product_config import system_config

        assistant = system_config.assistant
        return cls(
            default_model=assistant.default_model,
            default_reasoning_effort=assistant.default_reasoning_effort,
            models=[
                ModelRead(
                    id=model.id,
                    name=model.name,
                    provider=model.provider,
                    vision=model.features.vision,
                    reasoning=model.features.reasoning,
                    supported_efforts=list(model.supported_efforts),
                    context_window=model.context_window,
                    max_output_tokens=model.max_output_tokens,
                    pricing=ModelPricingRead(
                        input_usd_per_m=model.pricing.input_usd_per_m,
                        output_usd_per_m=model.pricing.output_usd_per_m,
                        cached_read_usd_per_m=model.pricing.cached_read_usd_per_m,
                    ),
                    is_default=model.id == assistant.default_model,
                )
                for model in system_config.enabled_models()
            ],
        )


class ThreadRead(BaseModel):
    id: UUID
    title: str
    status: str
    created_at: datetime | None = Field(serialization_alias="createdAt")
    updated_at: datetime | None = Field(serialization_alias="updatedAt")

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    client_message_id: UUID = Field(alias="clientMessageId")
    content: str = Field(min_length=1)

    model_config = {"populate_by_name": True}


class ResumeDecision(BaseModel):
    """One approval decision: approve or reject, nothing else.

    An edit would let a client substitute tool arguments the server never
    previewed, and a free-text respond would bypass the decision entirely, so
    both are absent rather than merely discouraged.
    """

    decision: Literal["approve", "reject"]

    model_config = {"populate_by_name": True}

    def command(self) -> dict:
        return {"type": self.decision}


class ThreadStateRead(BaseModel):
    """A thread's durable conversation, read from the checkpointer.

    There is no run status: a turn is either still streaming, or the graph is
    paused on a pending interrupt, or it finished. Only the last of those leaves
    a trace worth reporting, and it is the interrupt itself.
    """

    status: str = Field(default="idle")
    messages: list[dict] = Field(default_factory=list)
    interrupts: list[dict] = Field(default_factory=list)
