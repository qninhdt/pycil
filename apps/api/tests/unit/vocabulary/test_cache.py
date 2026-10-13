from cachetools import TTLCache
from pydantic import BaseModel

from pycil.vocabulary.cache import ContentCache


class Value(BaseModel):
    text: str


def test_cache_detaches_values_replaces_evicts_and_expires():
    now = [0]
    cache = ContentCache(max_bytes=30, ttl=5)
    cache.values = TTLCache(maxsize=30, ttl=5, timer=lambda: now[0], getsizeof=len)
    original = Value(text="a")
    cache.put("one", original)
    original.text = "changed"
    read = cache.get("one", Value)
    assert read.text == "a"
    read.text = "changed again"
    assert cache.get("one", Value).text == "a"
    cache.put("one", Value(text="b"))
    cache.put("two", Value(text="c"))
    cache.put("three", Value(text="d"))
    assert cache.get("one", Value) is None
    assert cache.get("two", Value).text == "c"
    now[0] = 5
    assert cache.get("two", Value) is None
    cache.put("three", Value(text="x" * 31))
    assert cache.get("three", Value) is None
    cache.values["corrupt"] = b"{}"
    assert cache.get("corrupt", Value) is None
    assert "corrupt" not in cache.values
