"""The worker's broker: one Redis Stream consumer group for both content jobs.

A second worker joins the same consumer group rather than scanning for work of its
own, so starting one never steals a job a live worker is running.

Acknowledgement is Taskiq's default, ``when_saved``, and no handler overrides it
with an ``ack_type`` label. The important part is what it is *not*:
``when_received`` would ACK before the effect exists and lose the job on a crash.
No handler acknowledges manually either — that mode leaves the message pending
until ``Context.ack`` is called, and a handler that never calls it would have its
job redelivered forever. Recovery is instead the Stream's pending-entry reclaim
below.

Two bounds matter and are set here rather than left to a default:

- ``idle_timeout`` is how long a message may sit unacknowledged before another
  worker may claim it. It must exceed the longest real job, or a slow provider
  call gets duplicated and paid for twice.
- ``unacknowledged_batch_size`` caps how many pending entries one reclaim pass
  takes, so recovery cannot starve live consumption.
"""

from __future__ import annotations

from pycil.config import settings
from pycil.queue.contracts import CONSUMER_GROUP_NAME, STREAM_NAME
from taskiq_redis import RedisStreamBroker

# Word generation waits on a provider; question supply does too. Both are bounded
# by the API's own timeouts, and this reclaim window sits well above them so an
# ordinary slow call is never mistaken for a dead worker.
RECLAIM_IDLE_TIMEOUT_MS = 300_000

broker = RedisStreamBroker(
    url=settings.redis_url,
    queue_name=STREAM_NAME,
    consumer_group_name=CONSUMER_GROUP_NAME,
    maxlen=10_000,
    idle_timeout=RECLAIM_IDLE_TIMEOUT_MS,
    unacknowledged_batch_size=10,
)
