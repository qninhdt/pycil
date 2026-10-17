"""Observed native backends; names are supplied by their users."""

from cachetools import TTLCache
from opentelemetry import metrics

from pycil.infrastructure.kv_store import InMemoryStore

_meter = metrics.get_meter("pycil.store")
_requests = _meter.create_counter("pycil.store.requests", unit="{request}")
_evictions = _meter.create_counter("pycil.store.evictions", unit="{entry}")
_entries = _meter.create_gauge(
    "pycil.store.entries", unit="{entry}", description="Unexpired entries at last store mutation"
)
_capacity = _meter.create_gauge("pycil.store.capacity", unit="{entry}")


class _EvictionBackend[K, V](TTLCache[K, V, float]):
    def __init__(self, maxsize: int, ttl: float, attributes: dict[str, str]) -> None:
        super().__init__(maxsize=maxsize, ttl=ttl)
        self.attributes = attributes

    def popitem(self) -> tuple[K, V]:
        item = super().popitem()
        # TTL expiry and explicit invalidation bypass this native eviction hook.
        _evictions.add(1, self.attributes)
        return item


class ObservedInMemoryStore[K, V](InMemoryStore[K, V]):
    def __init__(self, max_entries: int, ttl: float, *, name: str) -> None:
        super().__init__(max_entries, ttl)
        self.attributes = {"store": name, "backend": "memory"}
        self.values = _EvictionBackend[K, V](max_entries, ttl, self.attributes)
        _entries.set(0, self.attributes)
        _capacity.set(max_entries, self.attributes)

    def get(self, key: K) -> V | None:
        with self.values.timer:
            outcome = "hit" if key in self.values else "miss"
            value = super().get(key)
        _requests.add(1, self.attributes | {"outcome": outcome})
        return value

    def put(self, key: K, value: V) -> None:
        super().put(key, value)
        _entries.set(len(self.values), self.attributes)

    def discard(self, key: K) -> None:
        super().discard(key)
        _entries.set(len(self.values), self.attributes)

    def clear(self) -> None:
        super().clear()
        _entries.set(0, self.attributes)
