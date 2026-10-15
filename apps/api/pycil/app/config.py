"""One strict product/runtime document; credentials remain deployment-owned."""

import os
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import Field, ValidationError, model_validator

from pycil.account.config import AccountPolicy, PlanPolicy
from pycil.account.plans import Feature, Plan
from pycil.assistant.config import AssistantPolicy
from pycil.infrastructure.configuration import NonnegativeInt, Policy, PositiveInt
from pycil.library.config import LibraryProduct
from pycil.study.config import LearningPolicy
from pycil.study.enums import ResponseFormat
from pycil.vocabulary.config import GenerationPolicy, SearchPolicy, VocabularyPolicy

PositiveSeconds = Annotated[float, Field(strict=True, gt=0)]


class AccountConfig(Policy):
    preferences: AccountPolicy
    plans: dict[Plan, PlanPolicy]


class VocabularyProduct(Policy):
    generation: GenerationPolicy
    search: SearchPolicy


class ProjectionPolicy(Policy):
    max_page_size: Annotated[int, Field(strict=True, ge=1, le=100)]
    max_summary_memberships: PositiveInt
    max_word_ids: Annotated[int, Field(strict=True, ge=1, le=30)]
    max_word_senses: Annotated[int, Field(strict=True, ge=1, le=500)]
    max_context_senses: Annotated[int, Field(strict=True, ge=1, le=100)]
    inline_sources: Annotated[int, Field(strict=True, ge=1, le=5)]
    inline_examples: Annotated[int, Field(strict=True, ge=1, le=2)]
    max_query_chars: Annotated[int, Field(strict=True, ge=1, le=200)]


class ProductPolicy(Policy):
    account: AccountConfig
    study: LearningPolicy
    vocabulary: VocabularyProduct
    assistant: AssistantPolicy
    library: LibraryProduct
    projections: ProjectionPolicy

    @model_validator(mode="after")
    def validate_product(self):
        if self.library.pagination.page_size > self.projections.max_page_size:
            raise ValueError("default page size exceeds API read bound")
        if set(self.account.plans) != set(Plan):
            raise ValueError("every subscription plan must be configured")
        for plan, policy in self.account.plans.items():
            if len(policy.features) != len(set(policy.features)):
                raise ValueError("duplicate feature grant")
            if plan is Plan.FREE and Feature.ADVANCED_GRADING in policy.features:
                raise ValueError("Free must not grant advanced grading")
        by_id = {model.id: model for model in self.assistant.models}
        if len(by_id) != len(self.assistant.models):
            raise ValueError("duplicate model ID")
        default = by_id.get(self.assistant.defaults.model)
        if default is None or self.assistant.defaults.effort not in default.efforts:
            raise ValueError("default assistant model/effort is unavailable")
        if self.study.defaults.formats != [ResponseFormat.SINGLE_CHOICE]:
            raise ValueError("default learning preferences must work for Free")
        return self


class CachePolicy(Policy):
    ttl_seconds: PositiveInt
    max_entries: PositiveInt


class CachesPolicy(Policy):
    user_id: CachePolicy
    words: CachePolicy
    senses: CachePolicy
    artifacts: CachePolicy


class GenerationRuntime(Policy):
    active_jobs: PositiveInt
    pending_jobs: NonnegativeInt
    timeout_seconds: PositiveSeconds
    status_retention_seconds: PositiveInt
    tool_wait_seconds: PositiveSeconds
    enrichment_batch_size: Annotated[int, Field(strict=True, ge=1, le=8)]
    artifact_batch_size: Annotated[int, Field(strict=True, ge=1, le=20)]


class AssistantRuntime(Policy):
    llm_timeout_seconds: PositiveSeconds
    lease_ttl_seconds: PositiveSeconds
    starts_per_minute: PositiveInt


class ProvidersPolicy(Policy):
    vocabulary: VocabularyPolicy


class ApplicationPool(Policy):
    size: PositiveInt
    max_overflow: NonnegativeInt
    timeout_seconds: PositiveSeconds
    connect_timeout_seconds: PositiveSeconds


class CheckpointPool(Policy):
    min_size: NonnegativeInt
    max_size: PositiveInt
    timeout_seconds: PositiveSeconds
    startup_timeout_seconds: PositiveSeconds

    @model_validator(mode="after")
    def pool_bounds(self):
        if self.min_size > self.max_size:
            raise ValueError("pool minimum exceeds maximum")
        return self


class DatabaseRuntime(Policy):
    application_pool: ApplicationPool
    checkpoint_pool: CheckpointPool


class RedisRuntime(Policy):
    connect_timeout_seconds: PositiveSeconds
    operation_timeout_seconds: PositiveSeconds


class IdentityRuntime(Policy):
    profile_timeout_seconds: PositiveSeconds
    jwks_timeout_seconds: PositiveSeconds
    jwks_lifespan_seconds: PositiveSeconds


class SearchRuntime(Policy):
    rebuild_batch_size: PositiveInt
    writer_heap_bytes: Annotated[int, Field(strict=True, ge=15000000)]
    writer_threads: PositiveInt
    poll_interval_seconds: PositiveSeconds
    ownership_retry_seconds: PositiveSeconds
    retry_jitter_seconds: Annotated[float, Field(strict=True, ge=0)]
    revision_batch_size: PositiveInt
    publication_timeout_seconds: PositiveSeconds
    startup_timeout_seconds: PositiveSeconds
    progress_timeout_seconds: PositiveSeconds


class LibraryRuntime(Policy):
    statement_timeout_ms: PositiveInt
    scope_timeout_seconds: PositiveSeconds


class HTTPRuntime(Policy):
    max_body_bytes: PositiveInt
    client_timeout_seconds: PositiveSeconds


class HealthRuntime(Policy):
    timeout_seconds: PositiveSeconds
    redis_timeout_seconds: PositiveSeconds


class LifecycleRuntime(Policy):
    cleanup_timeout_seconds: PositiveSeconds


class TracesRuntime(Policy):
    max_queue_size: PositiveInt
    max_export_batch_size: PositiveInt
    schedule_delay_seconds: PositiveSeconds
    export_timeout_seconds: PositiveSeconds

    @model_validator(mode="after")
    def batch_bounds(self):
        if self.max_export_batch_size > self.max_queue_size:
            raise ValueError("trace export batch exceeds queue capacity")
        return self


class MetricsRuntime(Policy):
    export_interval_seconds: PositiveSeconds
    export_timeout_seconds: PositiveSeconds
    shutdown_timeout_seconds: PositiveSeconds


class TelemetryRuntime(Policy):
    traces: TracesRuntime
    metrics: MetricsRuntime


class RuntimePolicy(Policy):
    caches: CachesPolicy
    generation: GenerationRuntime
    assistant: AssistantRuntime
    providers: ProvidersPolicy
    database: DatabaseRuntime
    redis: RedisRuntime
    identity: IdentityRuntime
    search: SearchRuntime
    library: LibraryRuntime
    http: HTTPRuntime
    health: HealthRuntime
    lifecycle: LifecycleRuntime
    telemetry: TelemetryRuntime


class AppConfig(Policy):
    product: ProductPolicy
    runtime: RuntimePolicy


class UniqueKeyLoader(yaml.SafeLoader):
    """YAML duplicate keys are errors, never silent last-value-wins policy."""


def _mapping(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[object, object]:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key: object = loader.construct_object(key_node)  # pyright: ignore[reportUnknownMemberType]
        if key in result:
            raise ValueError(f"Duplicate product-policy key: {key}")
        result[key] = loader.construct_object(value_node)  # pyright: ignore[reportUnknownMemberType]
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def load_config(path: Path | None = None) -> AppConfig:
    path = path or Path(
        os.environ.get("CONFIG_PATH", Path(__file__).resolve().parents[4] / "config/config.yaml")
    )
    try:
        data = yaml.load(path.read_text(), Loader=UniqueKeyLoader)
        return AppConfig.model_validate(data)
    except ValidationError as exc:
        fields = sorted({".".join(map(str, error["loc"])) or "root" for error in exc.errors()})
        raise ValueError("Invalid product policy at: " + ", ".join(fields)) from None
    except OSError, yaml.YAMLError:
        raise ValueError("Product policy is unreadable or malformed YAML") from None
