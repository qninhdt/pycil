from cachetools import TTLCache
from pydantic import BaseModel, ValidationError

type CacheKey = tuple[object, ...] | str | int


class ContentCache:
    def __init__(
        self,
        max_bytes: int = 32 * 1024 * 1024,
        ttl: int = 30,
    ) -> None:
        self.values = TTLCache[CacheKey, bytes, float](
            maxsize=max_bytes,
            ttl=ttl,
            getsizeof=lambda value: len(value),
        )

    def get[T: BaseModel](
        self,
        key: CacheKey,
        model: type[T],
    ) -> T | None:
        payload = self.values.get(key)
        if payload is None:
            return None

        try:
            return model.model_validate_json(payload)
        except ValidationError:
            self.discard(key)
            return None

    def put(self, key: CacheKey, value: BaseModel) -> None:
        payload = value.model_dump_json().encode("utf-8")

        if len(payload) > self.values.maxsize:
            self.discard(key)
            return

        self.values[key] = payload

    def discard(self, key: CacheKey) -> None:
        self.values.pop(key, None)

    def clear(self) -> None:
        self.values.clear()
