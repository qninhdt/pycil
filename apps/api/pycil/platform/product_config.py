"""Validated product policy loaded from the committed YAML configuration."""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_PATH_ENV = "PYCIL_CONFIG_PATH"
REASONING_EFFORTS = ("none", "low", "medium", "high")
_STRICT = ConfigDict(extra="forbid", frozen=True)


class PlanConfig(BaseModel):
    model_config = _STRICT
    monthly_credits: int = Field(gt=0)


class AppSection(BaseModel):
    model_config = _STRICT
    credit_usd_value: Decimal = Field(gt=Decimal("0"))
    plans: dict[str, PlanConfig]

    @model_validator(mode="after")
    def require_plans(self) -> AppSection:
        missing = {"free", "pro"} - set(self.plans)
        if missing:
            raise ValueError(f"app.plans must define {sorted(missing)}")
        return self


class LearningSection(BaseModel):
    model_config = _STRICT
    max_words_per_session: int = Field(gt=0)
    max_questions_per_round: int = Field(gt=0)
    session_ttl_seconds: int = Field(gt=0)
    rubric_grading_credits: Decimal = Field(ge=Decimal("0.001"))


class ContentSection(BaseModel):
    model_config = _STRICT
    singleflight_timeout_seconds: int = Field(gt=0)


class AssistantSection(BaseModel):
    model_config = _STRICT
    turn_timeout_seconds: int = Field(gt=0)
    max_tool_calls_per_turn: int = Field(gt=0)
    default_model: str
    default_reasoning_effort: str


class ModelPricing(BaseModel):
    model_config = _STRICT
    input_usd_per_m: Decimal = Field(ge=Decimal("0"))
    output_usd_per_m: Decimal = Field(ge=Decimal("0"))
    cached_read_usd_per_m: Decimal = Field(ge=Decimal("0"))
    cache_write_usd_per_m: Decimal | None = Field(default=None, ge=Decimal("0"))


class ModelFeatures(BaseModel):
    model_config = _STRICT
    vision: bool = False
    reasoning: bool = False


class ModelSpec(BaseModel):
    model_config = _STRICT
    id: str
    name: str
    provider: str
    enabled: bool = True
    pricing: ModelPricing
    features: ModelFeatures = Field(default_factory=ModelFeatures)
    supported_efforts: list[str] = Field(default_factory=lambda: ["none"])
    context_window: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_efforts(self) -> ModelSpec:
        unknown = [effort for effort in self.supported_efforts if effort not in REASONING_EFFORTS]
        if unknown:
            raise ValueError(f"models[{self.id}].supported_efforts has unknown {unknown}")
        if "none" not in self.supported_efforts:
            raise ValueError(f"models[{self.id}].supported_efforts must include 'none'")
        reasoning_efforts = [effort for effort in self.supported_efforts if effort != "none"]
        if reasoning_efforts and not self.features.reasoning:
            raise ValueError(
                f"models[{self.id}] advertises {reasoning_efforts} but features.reasoning is false"
            )
        if self.features.reasoning and not reasoning_efforts:
            raise ValueError(
                f"models[{self.id}] sets features.reasoning but offers no effort beyond 'none'"
            )
        return self


class SystemConfig(BaseModel):
    model_config = _STRICT
    app: AppSection
    learning: LearningSection
    content: ContentSection
    assistant: AssistantSection
    models: list[ModelSpec]

    @model_validator(mode="after")
    def validate_catalog(self) -> SystemConfig:
        ids = [model.id for model in self.models]
        duplicates = sorted({model_id for model_id in ids if ids.count(model_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate model id(s): {duplicates}")
        if not self.models:
            raise ValueError("models must not be empty")
        default = self.get_model(self.assistant.default_model)
        if default is None:
            raise ValueError(
                f"assistant.default_model {self.assistant.default_model!r} is not in models"
            )
        if not default.enabled:
            raise ValueError(f"assistant.default_model {default.id!r} is disabled")
        if self.assistant.default_reasoning_effort not in default.supported_efforts:
            raise ValueError(
                "assistant.default_reasoning_effort "
                f"{self.assistant.default_reasoning_effort!r} is not supported by {default.id!r}"
            )
        return self

    def get_model(self, model_id: str) -> ModelSpec | None:
        return next((model for model in self.models if model.id == model_id), None)

    def enabled_models(self) -> list[ModelSpec]:
        return [model for model in self.models if model.enabled]

    def resolve_selection(
        self, model_id: str | None = None, reasoning_effort: str | None = None
    ) -> tuple[ModelSpec, str]:
        chosen_id = model_id or self.assistant.default_model
        model = self.get_model(chosen_id)
        if model is None:
            raise ValueError(f"unknown_model: {chosen_id}")
        if not model.enabled:
            raise ValueError(f"model_not_enabled: {chosen_id}")
        effort = reasoning_effort
        if effort is None:
            effort = (
                self.assistant.default_reasoning_effort
                if chosen_id == self.assistant.default_model
                else "none"
            )
        if effort not in REASONING_EFFORTS:
            raise ValueError(f"unknown_reasoning_effort: {effort}")
        if effort not in model.supported_efforts:
            raise ValueError(f"unsupported_reasoning_effort: {chosen_id}/{effort}")
        return model, effort


def resolve_config_path() -> Path:
    configured = os.environ.get(CONFIG_PATH_ENV)
    if configured:
        return Path(configured).resolve()
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "config" / "config.yaml"
        if candidate.is_file():
            return candidate
    return Path(__file__).resolve().parents[3] / "config" / "config.yaml"


def load_system_config(path: Path | None = None) -> SystemConfig:
    resolved = path or resolve_config_path()
    if not resolved.is_file():
        raise RuntimeError(f"system configuration not found at {resolved}")
    with resolved.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise RuntimeError(f"system configuration at {resolved} is not a mapping")
    return SystemConfig.model_validate(data)


_system_config: SystemConfig | None = None


def get_system_config() -> SystemConfig:
    global _system_config
    if _system_config is None:
        _system_config = load_system_config()
    return _system_config


class _SystemConfigProxy:
    def __getattr__(self, name: str):
        return getattr(get_system_config(), name)

    def __repr__(self) -> str:
        return repr(get_system_config())

    def __dir__(self) -> list[str]:
        return dir(get_system_config())


system_config = _SystemConfigProxy()
