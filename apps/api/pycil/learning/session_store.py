"""Redis-backed ephemeral study-session state.

The queue and issued-question binding deliberately live only in Redis.  Durable
attempt and response records are introduced by Phase 4; this module only makes
the transient delivery lifecycle retry-safe.
"""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import WatchError

_TTL_SECONDS = 8 * 3600
_GENERATION_QUOTA_WINDOW_SECONDS = 300


@dataclass(frozen=True)
class QueuedSense:
    sense_id: int
    mastery: int


@dataclass(frozen=True)
class SessionState:
    owner_id: UUID
    node_id: UUID
    scope_generation: int
    queue: list[QueuedSense]
    cursor: int
    issue: dict | None
    expires_at: datetime


def _key(session_id: str) -> str:
    return f"session:{session_id}"


async def create(
    redis: Redis,
    session_id: str,
    *,
    owner_id: UUID,
    node_id: UUID,
    scope_generation: int,
    queue: list[QueuedSense],
) -> SessionState:
    expires_at = (datetime.now(UTC) + timedelta(seconds=_TTL_SECONDS)).replace(
        microsecond=0
    )
    await redis.hset(
        _key(session_id),
        mapping={
            "owner": str(owner_id),
            "node": str(node_id),
            "generation": str(scope_generation),
            "queue": json.dumps([asdict(item) for item in queue]),
            "cursor": "0",
            "expires_at": expires_at.isoformat(),
        },
    )
    await redis.expire(_key(session_id), _TTL_SECONDS)
    return SessionState(owner_id, node_id, scope_generation, queue, 0, None, expires_at)


async def get(redis: Redis, session_id: str) -> SessionState | None:
    raw = await redis.hgetall(_key(session_id))
    if not raw:
        return None
    issue = json.loads(raw["issue"]) if raw.get("issue") else None
    return SessionState(
        owner_id=UUID(raw["owner"]),
        node_id=UUID(raw["node"]),
        scope_generation=int(raw["generation"]),
        queue=[QueuedSense(**item) for item in json.loads(raw["queue"])],
        cursor=int(raw["cursor"]),
        issue=issue,
        expires_at=datetime.fromisoformat(raw["expires_at"]),
    )


async def reserve_issue(redis: Redis, session_id: str, issue: dict) -> bool:
    """Atomically reserve one current issue; concurrent callers see pending."""
    key = _key(session_id)
    while True:
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                owner, current_issue = await pipe.hmget(key, "owner", "issue")
                if not owner or current_issue:
                    return False
                pipe.multi()
                pipe.hset(key, "issue", json.dumps(issue))
                pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()
                return True
            except WatchError:
                continue


async def replace_issue(redis: Redis, session_id: str, issue: dict) -> bool:
    """Replace an issue only while the full session state still exists."""
    key = _key(session_id)
    while True:
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                if not await pipe.hget(key, "owner"):
                    return False
                pipe.multi()
                pipe.hset(key, "issue", json.dumps(issue))
                pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()
                return True
            except WatchError:
                continue


async def clear_issue(redis: Redis, session_id: str) -> bool:
    key = _key(session_id)
    while True:
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                if not await pipe.hget(key, "owner"):
                    return False
                pipe.multi()
                pipe.hdel(key, "issue")
                await pipe.execute()
                return True
            except WatchError:
                continue


async def take_generation_slot(redis: Redis, owner_id: UUID, *, limit: int = 5) -> bool:
    """Bound costly generation scheduling per learner over a short window."""
    key = f"session:generation-quota:{owner_id}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, _GENERATION_QUOTA_WINDOW_SECONDS)
    return count <= limit


async def take_grading_slot(redis: Redis, owner_id: UUID, *, limit: int = 20) -> bool:
    """Bound expensive LLM grading per learner over the same short window."""
    key = f"session:grading-quota:{owner_id}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, _GENERATION_QUOTA_WINDOW_SECONDS)
    return count <= limit


async def claim_issue(redis: Redis, session_id: str, question_id: int) -> dict | None:
    """CAS ready -> answering so exactly one answer can enter grading."""
    key = _key(session_id)
    while True:
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                raw = await pipe.hget(key, "issue")
                if not raw:
                    return None
                issue = json.loads(raw)
                if issue.get("state") != "ready" or issue.get("question_id") != question_id:
                    return None
                issue["state"] = "answering"
                issue["lease_until"] = (
                    datetime.now(UTC) + timedelta(minutes=5)
                ).replace(microsecond=0).isoformat()
                pipe.multi()
                pipe.hset(key, "issue", json.dumps(issue))
                pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()
                return issue
            except WatchError:
                continue


async def restore_ready_issue(redis: Redis, session_id: str, issue: dict) -> bool:
    """Allow a retry if authoritative grading failed before its DB commit."""
    key = _key(session_id)
    while True:
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                raw = await pipe.hget(key, "issue")
                if not raw or not await pipe.hget(key, "owner"):
                    return False
                current = json.loads(raw)
                if (
                    current.get("state") != "answering"
                    or current.get("question_id") != issue.get("question_id")
                ):
                    return False
                pipe.multi()
                pipe.hset(key, "issue", json.dumps({**issue, "state": "ready"}))
                pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()
                return True
            except WatchError:
                continue


async def complete_issue(redis: Redis, session_id: str, question_id: int) -> bool:
    """CAS answering -> next cursor after a successful grading transaction."""
    key = _key(session_id)
    while True:
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                owner, raw_issue, raw_cursor = await pipe.hmget(
                    key, "owner", "issue", "cursor"
                )
                if not owner or not raw_issue or raw_cursor is None:
                    return False
                issue = json.loads(raw_issue)
                if issue.get("state") != "answering" or issue.get("question_id") != question_id:
                    return False
                pipe.multi()
                pipe.hset(key, "cursor", str(int(raw_cursor) + 1))
                pipe.hdel(key, "issue")
                pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()
                return True
            except WatchError:
                continue
