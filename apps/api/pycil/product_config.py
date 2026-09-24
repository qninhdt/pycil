"""Typed product policy loaded from the committed ``config/config.yaml``.

This module owns every *tunable* value an operator or product owner may change:
plan allowances, session and grading policy, content-job bounds, assistant turn
budgets and the model catalog with its tariffs. Credentials and deployment
addresses are deliberately *not* here — they live in :mod:`pycil.config` as
environment settings, so a committed file never holds a secret.

The file is read once per process and validated strictly. Unknown keys, a
duplicate model id, a default model that is absent or disabled, a default
reasoning effort its model does not support, a negative tariff or a non-positive
duration all fail at startup with the offending field named. There is no silent
fallback: a missing file or a bad value stops the process rather than letting a
default quietly change what a learner is charged or how long a session runs.
"""

from __future__ import annotations

import os
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

# One explicit deployment location. Inside an image the YAML is copied to a
# fixed path and named here; nothing is inferred from the caller's CWD, so two
# processes started from different directories cannot read different catalogs.
CONFIG_PATH_ENV = "PYCIL_CONFIG_PATH"

#: Reasoning levels a model may advertise. ``none`` means "do not send the
#: parameter at all" rather than "send the string none" — the provider treats an
#: absent field and an explicit ``none`` differently on some routes.
REASONING_EFFORTS = ("none", "low", "medium", "high")

#: The five YAML sections, in the order the file must declare them. Order is
#: checked because the models table is the long reference section and is meant to
#: sit last, where it does not push the short policy values off a reader's screen.
SECTION_ORDER = ("app", "learning", "content", "assistant", "models")

_STRICT = ConfigDict(extra="forbid", frozen=True)


class PlanConfig(BaseModel):
    """One account plan's monthly allowance, in whole Credits."""

    model_config = _STRICT

    monthly_credits: int = Field(gt=0)


class AppSection(BaseModel):
    model_config = _STRICT

    # 1 Credit = 0.001 USD. The ledger stores milli-credits, so this is the
    # single conversion factor between the displayed unit and the stored one.
    credit_usd_value: Decimal = Field(gt=Decimal("0"))
    plans: dict[str, PlanConfig]

    @model_validator(mode="after")
    def _require_both_plans(self) -> AppSection:
        missing = {"free", "pro"} - set(self.plans)
        if missing:
            raise ValueError(f"app.plans must define {sorted(missing)}")
        return self


class LearningSection(BaseModel):
    model_config = _STRICT

    max_words_per_session: int = Field(gt=0)
    max_questions_per_round: int = Field(gt=0)
    session_ttl_seconds: int = Field(gt=0)
    # Cost of one rubric evaluation, in whole Credits. Independent of how deep
    # the graded answer was, so a learner cannot be charged more for the same
    # evaluation by answering at a higher level.
    #
    # The floor is one milli-credit, not merely positive: the ledger stores
    # milli-credits, so a smaller value rounds to zero and then divides by zero in
    # the credit estimate and trips the "amount must be positive" guard on the
    # grading debit.
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
    """Provider tariffs in USD per million tokens."""

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
    #: Disabled entries stay in the file as a record of a considered model but
    #: are never selectable and never reach the public catalog projection.
    enabled: bool = True
    pricing: ModelPricing
    features: ModelFeatures = Field(default_factory=ModelFeatures)
    #: Reasoning levels this specific model accepts. A model without reasoning
    #: support advertises only ``none``.
    supported_efforts: list[str] = Field(default_factory=lambda: ["none"])
    context_window: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)

    @model_validator(mode="after")
    def _efforts_match_capability(self) -> ModelSpec:
        unknown = [e for e in self.supported_efforts if e not in REASONING_EFFORTS]
        if unknown:
            raise ValueError(f"models[{self.id}].supported_efforts has unknown {unknown}")
        if "none" not in self.supported_efforts:
            raise ValueError(f"models[{self.id}].supported_efforts must include 'none'")
        # A model that cannot reason must not advertise a reasoning level, and one
        # that can must offer at least one beyond "none". Without this the two
        # fields can disagree and a turn would request an effort the provider
        # ignores, which looks like reasoning being silently switched off.
        beyond_none = [e for e in self.supported_efforts if e != "none"]
        if beyond_none and not self.features.reasoning:
            raise ValueError(
                f"models[{self.id}] advertises {beyond_none} but features.reasoning is false"
            )
        if self.features.reasoning and not beyond_none:
            raise ValueError(
                f"models[{self.id}] sets features.reasoning but offers no effort beyond 'none'"
            )
        return self


class SystemConfig(BaseModel):
    """The whole committed policy, validated as one object."""

    model_config = _STRICT

    app: AppSection
    learning: LearningSection
    content: ContentSection
    assistant: AssistantSection
    models: list[ModelSpec]

    @model_validator(mode="after")
    def _catalog_and_default_agree(self) -> SystemConfig:
        ids = [m.id for m in self.models]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
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
                f"assistant.default_reasoning_effort "
                f"{self.assistant.default_reasoning_effort!r} is not supported by {default.id!r}"
            )
        return self

    def get_model(self, model_id: str) -> ModelSpec | None:
        for model in self.models:
            if model.id == model_id:
                return model
        return None

    def enabled_models(self) -> list[ModelSpec]:
        """The catalog subset safe to expose to a client."""
        return [m for m in self.models if m.enabled]

    def _billable_model(self, model_id: str) -> ModelSpec:
        """The catalog entry to bill against, or a refusal.

        An unknown or disabled id raises rather than falling back to the default
        model's tariff: silently billing one model's usage at another's price is
        the kind of substitution that only shows up as an unexplainable invoice,
        and the caller is the only place that knows which fallback is correct.
        """
        model = self.get_model(model_id)
        if model is None:
            raise ValueError(f"unknown_model: {model_id}")
        if not model.enabled:
            raise ValueError(f"model_not_enabled: {model_id}")
        return model

    def resolve_selection(
        self, model_id: str | None = None, reasoning_effort: str | None = None
    ) -> tuple[ModelSpec, str]:
        """The model and effort a turn will actually run with, or a refusal.

        A client may omit either field to take the default. Supplying one is a
        request to be validated, not an instruction: an unknown or disabled model
        and an effort the chosen model does not accept are both rejected here,
        before any provider call or ledger entry, so a bad selection costs the
        learner nothing and never reaches a gateway to fail later.
        """
        chosen_id = model_id or self.assistant.default_model
        model = self.get_model(chosen_id)
        if model is None:
            raise ValueError(f"unknown_model: {chosen_id}")
        if not model.enabled:
            raise ValueError(f"model_not_enabled: {chosen_id}")

        effort = reasoning_effort
        if effort is None:
            # The configured default only applies to the configured default model;
            # another model may not accept it, so it falls back to "none".
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

    def calculate_cost_usd(
        self,
        model_id: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> Decimal:
        """Provider cost for one turn's reported token usage.

        Cache reads and writes are reported within input totals, so they are
        removed from uncached input and billed at their own configured rates.
        """
        model = self._billable_model(model_id)
        input_tokens = max(0, input_tokens)
        output_tokens = max(0, output_tokens)
        cached_tokens = min(max(0, cached_tokens), input_tokens)
        cache_write_tokens = min(
            max(0, cache_write_tokens), input_tokens - cached_tokens
        )
        if cache_write_tokens and model.pricing.cache_write_usd_per_m is None:
            raise ValueError(f"cache_write_price_missing: {model_id}")
        uncached_input = max(0, input_tokens - cached_tokens - cache_write_tokens)
        cost = (
            (Decimal(uncached_input) * model.pricing.input_usd_per_m)
            + (Decimal(cached_tokens) * model.pricing.cached_read_usd_per_m)
            + (Decimal(output_tokens) * model.pricing.output_usd_per_m)
        )
        if cache_write_tokens and model.pricing.cache_write_usd_per_m is not None:
            cost += Decimal(cache_write_tokens) * model.pricing.cache_write_usd_per_m
        return cost / Decimal(1_000_000)

    def calculate_milli_credits(
        self,
        model_id: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> int:
        """The same cost expressed in the ledger's milli-credit unit.

        A very cheap turn is rounded once at the ledger's milli-credit precision.
        No usage costs zero, and there is no artificial minimum charge.
        """
        if (input_tokens + output_tokens + cache_write_tokens) <= 0:
            return 0
        cost_usd = self.calculate_cost_usd(
            model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            cache_write_tokens=cache_write_tokens,
        )
        milli = (cost_usd / self.app.credit_usd_value * Decimal(1000)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        return max(0, int(milli))


def resolve_config_path() -> Path:
    """The one location the YAML is read from, resolved without guessing.

    A packaged deployment sets :data:`CONFIG_PATH_ENV` to the fixed path its
    image copied the file to. Otherwise the path is derived from this module's
    own location, which is stable regardless of the working directory a process
    was started from. The file must exist; there is no CWD fallback, because a
    fallback is how two processes end up serving different catalogs.
    """
    configured = os.environ.get(CONFIG_PATH_ENV)
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[3] / "config" / "config.yaml"


def load_system_config(path: Path | None = None) -> SystemConfig:
    resolved = path or resolve_config_path()
    if not resolved.is_file():
        raise RuntimeError(f"system configuration not found at {resolved}")
    with resolved.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise RuntimeError(f"system configuration at {resolved} is not a mapping")
    declared = tuple(data)
    if declared != SECTION_ORDER:
        raise RuntimeError(
            f"system configuration sections must be {list(SECTION_ORDER)}, got {list(declared)}"
        )
    return SystemConfig.model_validate(data)


_system_config: SystemConfig | None = None


def get_system_config() -> SystemConfig:
    """The validated policy for this process, parsed on first use and then fixed."""
    global _system_config
    if _system_config is None:
        _system_config = load_system_config()
    return _system_config


class _SystemConfigProxy:
    """Attribute access without importing the parsed object at module load.

    Importing this module must not read the filesystem, so the singleton is
    reached through a proxy that parses on first attribute access.
    """

    def __getattr__(self, name: str):
        return getattr(get_system_config(), name)


system_config = _SystemConfigProxy()
