"""One validated product-policy document, with separate deployment credentials."""

import os
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

import yaml
from lexi_ai import ALLOWED_PAIRS, DecisionMode, QuestionType, ResponseFormat
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator
from sqlalchemy.engine import make_url

from pycil.account.plans import Feature, Plan

PositiveInt = Annotated[int, Field(strict=True, gt=0)]
NonnegativeInt = Annotated[int, Field(strict=True, ge=0)]


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class PlanPolicy(Policy):
    monthly_allowance_units: NonnegativeInt
    features: list[Feature]


class AccountDefaults(Policy):
    locale: str
    timezone: str
    translation_language: str


class AccountPolicy(Policy):
    defaults: AccountDefaults
    locales: list[str]
    translation_languages: list[str]

    @model_validator(mode="after")
    def validate_defaults(self):
        try:
            ZoneInfo(self.defaults.timezone)
        except (KeyError, ValueError) as exc:
            raise ValueError("invalid default timezone") from exc
        for values in (self.locales, self.translation_languages):
            if not values or len(values) != len(set(values)) or any(not v.strip() for v in values):
                raise ValueError("supported language lists must be nonempty and unique")
        if self.defaults.locale not in self.locales:
            raise ValueError("default locale is unsupported")
        if self.defaults.translation_language not in self.translation_languages:
            raise ValueError("default translation language is unsupported")
        return self


class LearningPreferences(Policy):
    question_types: list[QuestionType]
    formats: list[ResponseFormat]
    questions_per_sense: PositiveInt
    max_sense_count: PositiveInt
    show_explanations: Annotated[bool, Field(strict=True)]

    @model_validator(mode="after")
    def validate_selection(self):
        for values in (self.question_types, self.formats):
            if not values or len(set(values)) != len(values):
                raise ValueError("type/format selections must be nonempty and unique")
        feasible = any(
            any((kind, fmt) in ALLOWED_PAIRS for fmt in self.formats)
            for kind in self.question_types
        )
        if not feasible:
            raise ValueError("infeasible question selection")
        return self


class LearningLimits(Policy):
    min_questions_per_sense: PositiveInt
    max_questions_per_sense: Annotated[int, Field(strict=True, ge=1, le=7)]
    max_questions_per_prepare: Annotated[int, Field(strict=True, ge=1, le=100)]
    candidate_read_batch_size: PositiveInt
    max_answer_chars: PositiveInt
    max_review_batch: Annotated[int, Field(strict=True, ge=1, le=100)] = 100
    max_summary_nodes: Annotated[int, Field(strict=True, ge=1, le=50)] = 50
    max_activity_days: Annotated[int, Field(strict=True, ge=1, le=366)] = 366
    max_schedule_days: Annotated[int, Field(strict=True, ge=1, le=30)] = 30


class FormatMix(Policy):
    max_single_word: NonnegativeInt
    max_short_answer: NonnegativeInt


class FSRSPolicy(Policy):
    desired_retention: Annotated[float, Field(gt=0, lt=1)]
    max_interval_days: PositiveInt


class LearningPolicy(Policy):
    defaults: LearningPreferences
    limits: LearningLimits
    pair_levels: dict[
        QuestionType, dict[ResponseFormat, Annotated[int, Field(strict=True, ge=1, le=4)]]
    ]
    format_mix: dict[str, FormatMix]
    fsrs: FSRSPolicy

    @model_validator(mode="after")
    def validate_policy(self):
        pairs = {(kind, fmt) for kind, formats in self.pair_levels.items() for fmt in formats}
        if not pairs or not pairs <= ALLOWED_PAIRS:
            raise ValueError("unknown or unsupported type/format policy")
        if set(self.format_mix) != {"NEW", "AGAIN", "HARD", "GOOD", "EASY"}:
            raise ValueError("format mix must cover new and every native rating")
        self.validate_preferences(self.defaults)
        return self

    def validate_preferences(self, preferences: LearningPreferences):
        k = preferences.questions_per_sense
        if not self.limits.min_questions_per_sense <= k <= self.limits.max_questions_per_sense:
            raise ValueError("questions_per_sense outside configured bounds")
        if preferences.max_sense_count * k > self.limits.max_questions_per_prepare:
            raise ValueError("maximum prepared questions exceeded")
        feasible = any(
            any(fmt in self.pair_levels.get(kind, {}) for fmt in preferences.formats)
            for kind in preferences.question_types
        )
        if not feasible:
            raise ValueError("no product-enabled question type/format pair")


class WorkerPolicy(Policy):
    poll_interval_seconds: Annotated[float, Field(gt=0)]
    attempt_timeout_seconds: PositiveInt
    max_attempts: PositiveInt
    retry_delay_seconds: Annotated[float, Field(ge=0)]


class GenerationPolicy(Policy):
    questions_per_type: Annotated[int, Field(strict=True, ge=1, le=20)]
    distractor_count: Annotated[int, Field(strict=True, ge=3, le=20)]
    examples_per_sense: PositiveInt
    worker: WorkerPolicy


class AssistantPolicy(Policy):
    default_model: str
    default_effort: str
    llm_timeout_seconds: PositiveInt
    max_tool_calls: PositiveInt
    max_message_chars: PositiveInt
    max_context_messages: PositiveInt
    max_images: PositiveInt
    max_image_bytes: PositiveInt
    starts_per_minute: PositiveInt
    retention_days: PositiveInt
    purge_interval_seconds: PositiveInt
    purge_batch_size: PositiveInt


class ModelPolicy(Policy):
    id: str
    name: str
    vision: Annotated[bool, Field(strict=True)]
    efforts: list[str]
    max_output_tokens: PositiveInt
    input_units_per_token: Annotated[Decimal, Field(ge=0)]
    output_units_per_token: Annotated[Decimal, Field(ge=0)]
    cached_read_units_per_token: Annotated[Decimal, Field(ge=0)]
    cache_write_units_per_token: Annotated[Decimal, Field(ge=0)] | None

    @model_validator(mode="after")
    def validate_model(self):
        if not self.id.strip() or not self.name.strip():
            raise ValueError("model identifiers must not be blank")
        if not self.efforts or len(set(self.efforts)) != len(self.efforts):
            raise ValueError("model efforts must be nonempty and unique")
        if any(not effort.strip() for effort in self.efforts):
            raise ValueError("model effort must not be blank")
        if any(effort not in {"low", "medium", "high"} for effort in self.efforts):
            raise ValueError("model effort must be one of: low, medium, high")
        return self


class LexiPolicy(Policy):
    model: str
    timeout_seconds: Annotated[int, Field(strict=True, ge=1, le=120)]
    max_completion_tokens: Annotated[int, Field(strict=True, ge=1, le=16384)]
    max_retries: NonnegativeInt
    structured_outputs: Annotated[bool, Field(strict=True)]
    reasoning_effort: str | None
    temperature: Annotated[float, Field(ge=0, le=2)] | None
    decision_model: str
    decision_fallback_model: str
    decision_threshold: Annotated[float, Field(gt=0, le=1)]
    decision_mode: DecisionMode


class ProvidersPolicy(Policy):
    lexi: LexiPolicy


class LibraryPolicy(Policy):
    max_depth: PositiveInt
    page_size: PositiveInt
    max_senses_per_deck: PositiveInt
    max_children_per_folder: PositiveInt
    max_owned_nodes: PositiveInt
    max_owned_memberships: PositiveInt
    max_scope_nodes: PositiveInt
    max_scope_memberships: PositiveInt
    statement_timeout_ms: PositiveInt
    scope_timeout_seconds: PositiveInt


class CachePolicy(Policy):
    actor_ttl_seconds: PositiveInt
    deck_ttl_seconds: PositiveInt
    max_entries: PositiveInt
    max_value_bytes: PositiveInt


class ProjectionPolicy(Policy):
    max_page_size: Annotated[int, Field(strict=True, ge=1, le=100)] = 100
    max_summary_memberships: PositiveInt = 200000
    max_word_ids: Annotated[int, Field(strict=True, ge=1, le=30)] = 30
    max_word_senses: Annotated[int, Field(strict=True, ge=1, le=500)] = 500
    max_context_senses: Annotated[int, Field(strict=True, ge=1, le=100)] = 100
    inline_sources: Annotated[int, Field(strict=True, ge=1, le=5)] = 5
    inline_examples: Annotated[int, Field(strict=True, ge=1, le=2)] = 2
    max_query_chars: Annotated[int, Field(strict=True, ge=1, le=200)] = 200


class HTTPPolicy(Policy):
    max_body_bytes: PositiveInt


class ProductConfig(Policy):
    projections: ProjectionPolicy = Field(default_factory=ProjectionPolicy)
    plans: dict[Plan, PlanPolicy]
    account: AccountPolicy
    learning: LearningPolicy
    generation: GenerationPolicy
    assistant: AssistantPolicy
    models: list[ModelPolicy]
    providers: ProvidersPolicy
    library: LibraryPolicy
    cache: CachePolicy
    http: HTTPPolicy

    @model_validator(mode="after")
    def validate_product(self):
        if self.library.page_size > self.projections.max_page_size:
            raise ValueError("default page size exceeds API read bound")
        if set(self.plans) != set(Plan):
            raise ValueError("every subscription plan must be configured")
        for plan, policy in self.plans.items():
            if len(policy.features) != len(set(policy.features)):
                raise ValueError("duplicate feature grant")
            if plan is Plan.FREE and Feature.ADVANCED_GRADING in policy.features:
                raise ValueError("Free must not grant advanced grading")
        by_id = {model.id: model for model in self.models}
        if len(by_id) != len(self.models):
            raise ValueError("duplicate model ID")
        default = by_id.get(self.assistant.default_model)
        if default is None or self.assistant.default_effort not in default.efforts:
            raise ValueError("default assistant model/effort is unavailable")
        if self.learning.defaults.formats != [ResponseFormat.SINGLE_CHOICE]:
            raise ValueError("default learning preferences must work for Free")
        return self


class Deployment(Policy):
    db_url: SecretStr
    redis_url: SecretStr
    clerk_jwks_url: str
    clerk_issuer: str
    clerk_audience: str | None
    clerk_secret_key: SecretStr
    allowed_origins: list[str]
    cambridge_path: Path
    inference_api_key: SecretStr
    inference_base_url: str
    decision_api_key: SecretStr
    decision_base_url: str

    @model_validator(mode="after")
    def validate_addresses(self):
        try:
            database = make_url(self.db_url.get_secret_value())
        except Exception:
            raise ValueError("invalid database address") from None
        if (
            database.drivername != "postgresql+asyncpg"
            or not database.database
            or not database.host
        ):
            raise ValueError("DB_URL must identify a PostgreSQL application database")
        from urllib.parse import urlsplit

        redis = urlsplit(self.redis_url.get_secret_value())
        if redis.scheme not in {"redis", "rediss"} or not redis.hostname:
            raise ValueError("REDIS_URL must identify a Redis server")
        for value in (
            self.clerk_jwks_url,
            self.clerk_issuer,
            self.inference_base_url,
            self.decision_base_url,
        ):
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("service URLs must be HTTP(S) without embedded credentials")
        for value in self.allowed_origins:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("ALLOWED_ORIGINS must contain explicit HTTP(S) origins")
        return self

    @classmethod
    def from_environment(cls):
        required = {
            "db_url": "DB_URL",
            "redis_url": "REDIS_URL",
            "clerk_jwks_url": "CLERK_JWKS_URL",
            "clerk_issuer": "CLERK_ISSUER",
            "clerk_secret_key": "CLERK_SECRET_KEY",
            "cambridge_path": "LEXI_CAMBRIDGE_DB_PATH",
            "inference_api_key": "INFERENCE_API_KEY",
            "inference_base_url": "INFERENCE_BASE_URL",
            "decision_api_key": "LEXI_DECISION_API_KEY",
            "decision_base_url": "LEXI_DECISION_BASE_URL",
        }
        missing = [key for key in required.values() if not os.getenv(key, "").strip()]
        if missing:
            raise ValueError("Missing deployment variables: " + ", ".join(sorted(missing)))
        try:
            return cls(
                **{key: os.environ[var] for key, var in required.items()},
                clerk_audience=os.getenv("CLERK_AUDIENCE") or None,
                allowed_origins=[
                    s.strip() for s in os.environ.get("ALLOWED_ORIGINS", "").split(",") if s.strip()
                ],
            )
        except ValueError, TypeError:
            # Validation errors may embed raw input, including database passwords.
            raise ValueError(
                "Invalid deployment configuration; check environment addresses"
            ) from None


class UniqueKeyLoader(yaml.SafeLoader):
    """YAML duplicate keys are errors, never silent last-value-wins policy."""


def _mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError(f"Duplicate product-policy key: {key}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def load_config(path: Path | None = None) -> ProductConfig:
    path = path or Path(
        os.environ.get("CONFIG_PATH", Path(__file__).resolve().parents[3] / "config/config.yaml")
    )
    try:
        data = yaml.load(path.read_text(), Loader=UniqueKeyLoader)
        return ProductConfig.model_validate(data)
    except ValidationError as exc:
        fields = sorted({".".join(map(str, error["loc"])) or "root" for error in exc.errors()})
        raise ValueError("Invalid product policy at: " + ", ".join(fields)) from None
    except OSError, yaml.YAMLError:
        raise ValueError("Product policy is unreadable or malformed YAML") from None
