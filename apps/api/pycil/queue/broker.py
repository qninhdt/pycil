"""The API's publish handle for content jobs.

The API publishes but never consumes, so this broker carries no task
registrations. It shares the stream name and consumer group with the worker's
broker so both ends address the same Stream, and it is created lazily so importing
a route module does not open a Redis connection.

Kept separate from the worker's broker on purpose: the API must not import worker
code, and the worker must not be able to serve an API request.
"""

from __future__ import annotations

from taskiq_redis import RedisStreamBroker

from pycil.config import settings
from pycil.queue.contracts import CONSUMER_GROUP_NAME, STREAM_NAME

_broker: RedisStreamBroker | None = None


def get_broker() -> RedisStreamBroker:
    """The process-wide publish broker.

    ``maxlen`` bounds the stream so a worker outage cannot grow Redis without
    limit. It is deliberately generous: trimming a message that has not been
    consumed yet loses that content job, and the plan accepts losing a
    reproducible content job on Redis pressure but not silently on every burst.
    """
    global _broker
    if _broker is None:
        _broker = RedisStreamBroker(
            url=settings.redis_url,
            queue_name=STREAM_NAME,
            consumer_group_name=CONSUMER_GROUP_NAME,
            maxlen=10_000,
        )
    return _broker
