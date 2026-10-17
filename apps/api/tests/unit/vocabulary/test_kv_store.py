import pytest
from cachetools import TTLCache
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from pydantic import BaseModel

from pycil.infrastructure.kv_store import InMemoryStore
from pycil.observability import stores as kv_store
from pycil.observability.stores import ObservedInMemoryStore


class Value(BaseModel):
    text: str


def test_kv_store_stores_objects_and_replaces_evicts_expires_and_clears():
    now = [0]
    store = InMemoryStore[str, Value](max_entries=2, ttl=5)
    store.values = TTLCache(maxsize=2, ttl=5, timer=lambda: now[0])
    original = Value(text="a")
    store.put("one", original)
    assert store.get("one") is original
    store.put("two", Value(text="b"))
    assert store.get("one") is original  # Access updates LRU, not expiry.
    store.put("three", Value(text="c"))
    assert store.get("two") is None
    store.put("one", Value(text="replacement"))
    assert store.get("one").text == "replacement"
    now[0] = 5
    assert store.get("one") is None
    store.put("one", original)
    store.discard("one")
    store.discard("absent")
    assert store.get("one") is None
    store.put("one", original)
    store.clear()
    assert not store.values


@pytest.mark.parametrize(
    "capacity,ttl",
    [(0, 1), (-1, 1), (True, 1), (1, 0), (1, -1), (1, True), (1, float("nan")), (1, float("inf"))],
)
def test_kv_store_rejects_invalid_capacity_and_expiration(capacity, ttl):
    with pytest.raises(ValueError):
        InMemoryStore(capacity, ttl)


@pytest.fixture
def cache_metrics(monkeypatch):
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    meter = provider.get_meter("pycil.store")
    for name, kind, unit in (
        ("requests", "counter", "{request}"),
        ("evictions", "counter", "{entry}"),
        ("entries", "gauge", "{entry}"),
        ("capacity", "gauge", "{entry}"),
    ):
        monkeypatch.setattr(
            kv_store, f"_{name}", getattr(meter, f"create_{kind}")(f"pycil.store.{name}", unit=unit)
        )

    def value(name, **attributes):
        data = reader.get_metrics_data()
        points = [
            (metric.name, point)
            for resource in data.resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
            for point in metric.data.data_points
        ]
        assert all(set(point.attributes) <= {"store", "backend", "outcome"} for _, point in points)
        assert "private-cache-key" not in str(data)
        return sum(
            point.value
            for metric_name, point in points
            if metric_name == f"pycil.store.{name}" and point.attributes == attributes
        )

    try:
        yield value
    finally:
        provider.shutdown()


def test_cache_metrics_count_real_hits_misses_and_lru_eviction(cache_metrics):
    store = ObservedInMemoryStore[str, str | None](max_entries=2, ttl=60, name="word")
    store.put("private-cache-key-A", None)
    store.put("private-cache-key-B", "B")
    assert store.get("private-cache-key-A") is None  # A cached None is still a hit.
    store.put("private-cache-key-C", "C")
    assert store.get("private-cache-key-B") is None
    assert store.get("private-cache-key-A") is None

    assert cache_metrics("requests", store="word", backend="memory", outcome="hit") == 2
    assert cache_metrics("requests", store="word", backend="memory", outcome="miss") == 1
    assert cache_metrics("evictions", store="word", backend="memory") == 1
    assert cache_metrics("entries", store="word", backend="memory") == 2
    assert cache_metrics("capacity", store="word", backend="memory") == 2


@pytest.mark.parametrize("removal", ["expiry", "discard", "clear", "replace"])
def test_cache_metrics_do_not_call_other_removals_capacity_evictions(cache_metrics, removal):
    store = ObservedInMemoryStore[str, str](max_entries=2, ttl=60, name="artifact")
    store.put("A", "A")
    store.put("B", "B")
    if removal == "expiry":
        assert len(store.values.expire(store.values.timer() + 60)) == 2
        assert store.get("A") is None
        store.put("C", "C")
        expected_entries = 1
    elif removal == "discard":
        store.discard("A")
        store.discard("absent")
        expected_entries = 1
    elif removal == "clear":
        store.clear()
        expected_entries = 0
    else:
        store.put("A", "replacement")
        expected_entries = 2

    assert cache_metrics("requests", store="artifact", backend="memory", outcome="hit") == 0
    assert cache_metrics("evictions", store="artifact", backend="memory") == 0
    assert cache_metrics("entries", store="artifact", backend="memory") == expected_entries
    assert cache_metrics("capacity", store="artifact", backend="memory") == 2


def test_standard_redis_keys_follow_domain_hierarchy():
    from uuid import uuid4

    from pycil.app.broker import CONSUMER_GROUP_NAME, TASK_RESULT_PREFIX, TASK_STREAM_KEY
    from pycil.assistant.conversations import conversation_lease_key
    from pycil.assistant.stream import (
        assistant_rate_limit_key,
        assistant_rate_limit_pattern,
    )
    from pycil.jobs.metadata import owner_key
    from pycil.study.tasks import study_request_key
    from pycil.vocabulary.generation.tasks import (
        word_generation_lock_key,
        word_request_key,
    )

    user_id = uuid4()
    job_id = "job-123"
    fingerprint = "fp-456"

    # Jobs domain
    assert TASK_STREAM_KEY == "pycil:jobs:tasks"
    assert CONSUMER_GROUP_NAME == "pycil-workers"
    assert TASK_RESULT_PREFIX == "pycil:jobs:result"
    assert owner_key(job_id) == f"pycil:jobs:owner:{job_id}"

    # Study domain
    assert study_request_key(user_id, fingerprint) == f"pycil:study:request:{user_id}:{fingerprint}"

    # Vocabulary domain
    assert (
        word_request_key(user_id, fingerprint)
        == f"pycil:vocabulary:request:{user_id}:{fingerprint}"
    )

    assert word_generation_lock_key("ref-789") == "pycil:vocabulary:generation:lock:ref-789"

    # Assistant domain
    conv_id = uuid4()
    assert conversation_lease_key(conv_id) == f"pycil:assistant:conversation:lease:{conv_id}"
    assert (
        assistant_rate_limit_key(user_id, 12345)
        == f"pycil:assistant:rate-limit:starts:{user_id}:12345"
    )
    assert assistant_rate_limit_pattern(user_id) == f"pycil:assistant:rate-limit:starts:{user_id}:*"
