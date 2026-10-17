from typing import Annotated

from pydantic import Field

from pycil.infrastructure.providers import ProviderPolicy
from pycil.utils.configuration import Policy, PositiveInt


class GenerationPolicy(Policy):
    examples_per_sense: PositiveInt = 5


class SearchPolicy(Policy):
    max_query_chars: Annotated[int, Field(strict=True, ge=1, le=256)] = 256
    default_limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 30


class SearchRuntime(Policy):
    rebuild_batch_size: PositiveInt = 2000
    writer_heap_bytes: Annotated[int, Field(strict=True, ge=15000000)] = 15000000
    writer_threads: PositiveInt = 1
    poll_interval_seconds: Annotated[float, Field(strict=True, gt=0)] = 2.0
    ownership_retry_seconds: Annotated[float, Field(strict=True, gt=0)] = 2.0
    retry_jitter_seconds: Annotated[float, Field(strict=True, ge=0)] = 0.2
    revision_batch_size: PositiveInt = 100
    publication_timeout_seconds: Annotated[float, Field(strict=True, gt=0)] = 30.0
    startup_timeout_seconds: Annotated[float, Field(strict=True, gt=0)] = 300.0
    progress_timeout_seconds: Annotated[float, Field(strict=True, gt=0)] = 30.0


class PreviewPolicy(Policy):
    max_word_ids: Annotated[int, Field(strict=True, ge=1, le=30)] = 30
    max_word_senses: Annotated[int, Field(strict=True, ge=1, le=500)] = 500
    max_context_senses: Annotated[int, Field(strict=True, ge=1, le=100)] = 100
    inline_sources: Annotated[int, Field(strict=True, ge=1, le=5)] = 5
    inline_examples: Annotated[int, Field(strict=True, ge=1, le=2)] = 2


class VocabularyConfig(Policy):
    search: SearchPolicy = SearchPolicy()
    preview: PreviewPolicy = PreviewPolicy()
    generation: GenerationPolicy = GenerationPolicy()
    search_runtime: SearchRuntime = SearchRuntime()
    enrichment_batch_size: Annotated[int, Field(strict=True, ge=1, le=8)] = 8
    provider: ProviderPolicy = Field(default_factory=ProviderPolicy)
