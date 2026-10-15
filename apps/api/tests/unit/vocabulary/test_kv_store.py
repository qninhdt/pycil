import pytest
from cachetools import TTLCache
from pydantic import BaseModel

from pycil.infrastructure.kv_store import InMemoryStore


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
