"""Local cache-only benchmark; run explicitly with pytest -s tests/benchmarks."""

import gc
import json
import platform
import statistics
import tracemalloc
from importlib.metadata import version
from time import perf_counter_ns
from uuid import UUID, uuid4

from pydantic import TypeAdapter

from pycil.app.config import load_config
from pycil.infrastructure.cache import MemoryCache, RedisCache
from pycil.study.artifacts.schemas import Artifact
from pycil.study.enums import QuestionArtifactType
from pycil.vocabulary.schemas import CachedWord, Word, sense_adapter
from tests.support.artifacts import payloads


def word_payload(senses):
    return Word.model_validate(
        {
            "id": 1,
            "lemma": "bank",
            "type": "word",
            "generation_state": "done",
            "aliases": ["lender", "banking house"],
            "senses": [
                {
                    "id": i + 1,
                    "word_id": 1,
                    "pos": "noun",
                    "tier": "core",
                    "definition": {"id": i + 1, "content": "a financial institution " * 8},
                    "examples": [
                        {"id": i * 5 + j + 1, "content": "The [bank] holds customer deposits. " * 4}
                        for j in range(5)
                    ],
                    "forms": [{"surface": "banks", "inf": "plural"}],
                    "patterns": ["bank on sth"],
                    "collocations": ["bank account", "bank manager"],
                }
                for i in range(senses)
            ],
        }
    ).model_dump_json()


def test_representative_cache_capacity():
    policy = load_config().runtime.caches
    # Decode independent DTOs: sharing nested lists/strings would undercount memory.
    word = Word.model_validate_json(word_payload(8))
    metadata_adapter = TypeAdapter(CachedWord)
    metadata = metadata_adapter.dump_json(
        CachedWord(
            id=word.id,
            lemma=word.lemma,
            type=word.type,
            generation_state=word.generation_state,
            aliases=tuple(word.aliases),
            related=tuple(word.related),
            sense_ids=tuple(sense.id for sense in word.senses),
        )
    )
    sense = sense_adapter.dump_json(word.senses[0])
    kind = QuestionArtifactType.WORD_DEFINITION
    artifact = Artifact(
        id=1, sense_id=1, theme_id=None, artifact_type=kind, payload=payloads()[kind]
    ).model_dump_json()
    reports = []
    for name, capacity, ttl, make, payload_bytes in [
        ("user_id", policy.user_id.max_entries, policy.user_id.ttl_seconds, lambda: uuid4(), 36),
        (
            "word_metadata",
            policy.words.max_entries,
            policy.words.ttl_seconds,
            lambda: metadata_adapter.validate_json(metadata),
            len(metadata),
        ),
        (
            "sense",
            policy.senses.max_entries,
            policy.senses.ttl_seconds,
            lambda: sense_adapter.validate_json(sense),
            len(sense),
        ),
        (
            "artifacts",
            policy.artifacts.max_entries,
            policy.artifacts.ttl_seconds,
            lambda: Artifact.model_validate_json(artifact),
            len(artifact.encode()),
        ),
    ]:
        gc.collect()
        tracemalloc.start()
        before, _ = tracemalloc.get_traced_memory()
        cache = MemoryCache(capacity, ttl)
        for i in range(capacity):
            key = f"user_{i:032x}" if name == "user_id" else i
            cache.put(key, make())
        current, peak = tracemalloc.get_traced_memory()
        assert len(cache.values) == capacity
        reports.append(
            {
                "cache": name,
                "entries": capacity,
                "json_bytes": payload_bytes,
                "allocated_mib": round((current - before) / 2**20, 3),
                "peak_mib": round((peak - before) / 2**20, 3),
            }
        )
        tracemalloc.stop()
        del cache
    print("CACHE_CAPACITY " + json.dumps(reports))


async def test_equivalent_uuid_hit_latency_has_no_database_work(redis_store):
    redis, namespace = redis_store
    value, key = uuid4(), "user_00000000000000000000000000000001"
    memory = MemoryCache[str, UUID](10000, 60)
    external = RedisCache(redis, UUID, f"{namespace}:uuid:v1", 60)
    memory.put(key, value)
    await external.put(key, value)
    samples = {"memory_ns": [], "redis_ns": []}
    for _ in range(5000):
        start = perf_counter_ns()
        assert memory.get(key) is value
        samples["memory_ns"].append(perf_counter_ns() - start)
    for _ in range(2000):
        start = perf_counter_ns()
        assert await external.get(key) == value
        samples["redis_ns"].append(perf_counter_ns() - start)
    report = {
        "python": platform.python_version(),
        "cachetools": version("cachetools"),
        "redis_client": version("redis"),
        "pydantic": version("pydantic"),
        "uuid_json_bytes": len(external.adapter.dump_json(value)),
    }
    for name, measurements in samples.items():
        ordered = sorted(measurements)
        report[name] = {
            "samples": len(ordered),
            "p50": statistics.median(ordered),
            "p95": ordered[int(len(ordered) * 0.95)],
        }
    print("CACHE_HITS " + json.dumps(report))
