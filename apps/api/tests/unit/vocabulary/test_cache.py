import pytest
from cachetools import TTLCache
from pydantic import BaseModel

from pycil.infrastructure.cache import MemoryCache


class Value(BaseModel):
    text: str


def test_cache_stores_objects_and_replaces_evicts_expires_and_clears():
    now = [0]
    cache = MemoryCache[str, Value](max_entries=2, ttl=5)
    cache.values = TTLCache(maxsize=2, ttl=5, timer=lambda: now[0])
    original = Value(text="a")
    cache.put("one", original)
    assert cache.get("one") is original
    cache.put("two", Value(text="b"))
    assert cache.get("one") is original  # Access updates LRU, not expiry.
    cache.put("three", Value(text="c"))
    assert cache.get("two") is None
    cache.put("one", Value(text="replacement"))
    assert cache.get("one").text == "replacement"
    now[0] = 5
    assert cache.get("one") is None
    cache.put("one", original)
    cache.discard("one")
    cache.discard("absent")
    assert cache.get("one") is None
    cache.put("one", original)
    cache.clear()
    assert not cache.values


@pytest.mark.parametrize(
    "capacity,ttl",
    [(0, 1), (-1, 1), (True, 1), (1, 0), (1, -1), (1, True), (1, float("nan")), (1, float("inf"))],
)
def test_cache_rejects_invalid_capacity_and_expiration(capacity, ttl):
    with pytest.raises(ValueError):
        MemoryCache(capacity, ttl)
