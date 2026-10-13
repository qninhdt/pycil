"""One validated product-policy document, with separate deployment credentials."""

import os
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import Field, ValidationError, model_validator

from pycil.account.config import AccountPolicy, PlanPolicy
from pycil.account.plans import Feature, Plan
from pycil.assistant.config import AssistantPolicy, ModelPolicy
from pycil.infrastructure.configuration import Policy, PositiveInt
from pycil.library.config import LibraryPolicy
from pycil.study.config import (
    LearningPolicy,
)
from pycil.study.enums import ResponseFormat
from pycil.vocabulary.config import GenerationPolicy, VocabularyPolicy


class ProvidersPolicy(Policy):
    vocabulary: VocabularyPolicy


class CachePolicy(Policy):
    actor_ttl_seconds: PositiveInt


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


def load_config(path: Path | None = None) -> ProductConfig:
    path = path or Path(
        os.environ.get("CONFIG_PATH", Path(__file__).resolve().parents[4] / "config/config.yaml")
    )
    try:
        data = yaml.load(path.read_text(), Loader=UniqueKeyLoader)
        return ProductConfig.model_validate(data)
    except ValidationError as exc:
        fields = sorted({".".join(map(str, error["loc"])) or "root" for error in exc.errors()})
        raise ValueError("Invalid product policy at: " + ", ".join(fields)) from None
    except OSError, yaml.YAMLError:
        raise ValueError("Product policy is unreadable or malformed YAML") from None
