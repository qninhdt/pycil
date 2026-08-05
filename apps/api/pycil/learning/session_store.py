"""Redis-backed ephemeral study-session state (session-scoped model).

This is the EPHEMERAL tier: admitted senses + per-sense checkpoint/score progress,
round bookkeeping, and per-sense served-question exclusions.  Only FSRS state is
durable (Postgres); everything here is discarded at session end and is safe to
lose — the authoritative one-FSRS-per-(session,sense) record lives in Postgres
(``session_sense_attempts`` + ``review_log``), written before any Redis update
(see Phase 7).  Redis ``score``/``fsrs_applied`` are an advisory fast-path only.

Key layout (namespace ``session:{sid}``):
  ``session:{sid}``                       HASH  meta (owner/node/generation/round/settings)
  ``session:{sid}:admitted``              HASH  sense_id -> purpose (``due``|``new``)
  ``session:{sid}:sense:{sense_id}``      HASH  per-sense progress
  ``session:{sid}:sense:{sense_id}:excluded`` SET  served question ids (int)

Round membership uses ``last_round_used`` on each sense hash (bounded), NOT a
per-round SET (no key-per-round sprawl).
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import WatchError

from pycil.learning.policy import MAX_RETRIES_PER_CHECKPOINT, REQUIRED_CHECKPOINTS

# TTL >= the pending-grade reconcile horizon (24h) so Redis expiry only ends an
# abandoned live session; it never races the durable async settle (which reads
# requested/served level from the ``responses`` row, not Redis).
_TTL_SECONDS = 24 * 3600
_GENERATION_QUOTA_WINDOW_SECONDS = 300

_NONE = "none"
_MISSING = "-"


# --- dataclasses ----------------------------------------------------------------


@dataclass(frozen=True)
class SessionMeta:
    owner_id: UUID
    node_id: UUID
    scope_generation: int
    round_index: int
    round_count: int
    target_words: int
    max_per_round: int
    expires_at: datetime


@dataclass(frozen=True)
class AdmittedSense:
    sense_id: int
    purpose: str  # "due" | "new"
    requested_levels: list[int]  # per-checkpoint requested level (N entries)


@dataclass
class SenseProgress:
    sense_id: int
    passed: int
    score: str  # "none" | "again" | "good"
    fsrs_applied: bool
    exposed: bool
    open_checkpoint: int | None
    retries_used: int
    open_requested_level: int | None
    open_failed_round: int | None
    awaiting_grade: bool
    last_round_used: int
    terminal: bool
    terminal_reason: str  # "" | "completed" | "retries_exhausted"
    requested_levels: list[int]


# --- key builders ---------------------------------------------------------------


def _key(session_id: str) -> str:
    return f"session:{session_id}"


def _admitted_key(session_id: str) -> str:
    return f"session:{session_id}:admitted"


def _sense_key(session_id: str, sense_id: int) -> str:
    return f"session:{session_id}:sense:{sense_id}"


def _excluded_key(session_id: str, sense_id: int) -> str:
    return f"session:{session_id}:sense:{sense_id}:excluded"


def _projected_key(session_id: str, sense_id: int) -> str:
    return f"session:{session_id}:sense:{sense_id}:projected"


def _opt_int(raw: str | None) -> int | None:
    return None if raw is None or raw == _MISSING else int(raw)


# --- creation / reads -----------------------------------------------------------


async def create(
    redis: Redis,
    session_id: str,
    *,
    owner_id: UUID,
    node_id: UUID,
    scope_generation: int,
    target_words: int,
    max_per_round: int,
    admitted: list[AdmittedSense],
) -> SessionMeta:
    """Write session meta + admitted set + initial per-sense progress with TTL."""
    expires_at = (datetime.now(UTC) + timedelta(seconds=_TTL_SECONDS)).replace(microsecond=0)
    key = _key(session_id)
    await redis.hset(
        key,
        mapping={
            "owner": str(owner_id),
            "node": str(node_id),
            "generation": str(scope_generation),
            "round_index": "0",
            "round_count": "0",
            "prepare_attempts": "0",
            "prepare_retry_at": "0",
            "target_words": str(target_words),
            "max_per_round": str(max_per_round),
            "expires_at": expires_at.isoformat(),
        },
    )
    await redis.expire(key, _TTL_SECONDS)

    if admitted:
        await redis.hset(
            _admitted_key(session_id),
            mapping={str(item.sense_id): item.purpose for item in admitted},
        )
        await redis.expire(_admitted_key(session_id), _TTL_SECONDS)

    for item in admitted:
        skey = _sense_key(session_id, item.sense_id)
        await redis.hset(
            skey,
            mapping={
                "passed": "0",
                "score": _NONE,
                "fsrs_applied": "0",
                "exposed": "0",
                "open_checkpoint": _MISSING,
                "retries_used": "0",
                "open_requested_level": _MISSING,
                "open_failed_round": _MISSING,
                "awaiting_grade": "0",
                "last_round_used": "0",
                "terminal": "0",
                "terminal_reason": "",
                "current_qid": _MISSING,
                "requested_levels": json.dumps(item.requested_levels),
            },
        )
        await redis.expire(skey, _TTL_SECONDS)

    return SessionMeta(
        owner_id=owner_id,
        node_id=node_id,
        scope_generation=scope_generation,
        round_index=0,
        round_count=0,
        target_words=target_words,
        max_per_round=max_per_round,
        expires_at=expires_at,
    )


async def get_meta(redis: Redis, session_id: str) -> SessionMeta | None:
    raw = await redis.hgetall(_key(session_id))
    if not raw:
        return None
    # A hash that exists but lacks the identity fields is not a session. That state
    # is reachable: `advance_round` writes `round_index` with HSET, which CREATES the
    # key if the session has expired between the caller's read and its own write, so
    # a partially-populated "zombie" can outlive the session it came from. Treating
    # it as absent is the honest reading — `session_not_found` is exactly what the
    # caller should see — whereas indexing straight into `raw` raised
    # `KeyError: 'owner'`, i.e. a 500 for an expired session.
    if "owner" not in raw or "node" not in raw:
        return None
    return SessionMeta(
        owner_id=UUID(raw["owner"]),
        node_id=UUID(raw["node"]),
        scope_generation=int(raw["generation"]),
        round_index=int(raw["round_index"]),
        round_count=int(raw["round_count"]),
        target_words=int(raw["target_words"]),
        max_per_round=int(raw["max_per_round"]),
        expires_at=datetime.fromisoformat(raw["expires_at"]),
    )


async def get_admitted(redis: Redis, session_id: str) -> dict[int, str]:
    """Return ``{sense_id: purpose}`` for the admitted set."""
    raw = await redis.hgetall(_admitted_key(session_id))
    return {int(sense_id): purpose for sense_id, purpose in raw.items()}


async def get_progress(redis: Redis, session_id: str, sense_id: int) -> SenseProgress | None:
    raw = await redis.hgetall(_sense_key(session_id, sense_id))
    if not raw:
        return None
    return SenseProgress(
        sense_id=sense_id,
        passed=int(raw["passed"]),
        score=raw["score"],
        fsrs_applied=raw["fsrs_applied"] == "1",
        exposed=raw["exposed"] == "1",
        open_checkpoint=_opt_int(raw.get("open_checkpoint")),
        retries_used=int(raw["retries_used"]),
        open_requested_level=_opt_int(raw.get("open_requested_level")),
        open_failed_round=_opt_int(raw.get("open_failed_round")),
        awaiting_grade=raw["awaiting_grade"] == "1",
        last_round_used=int(raw["last_round_used"]),
        terminal=raw["terminal"] == "1",
        terminal_reason=raw.get("terminal_reason", ""),
        requested_levels=json.loads(raw["requested_levels"]),
    )


async def excluded_ids(redis: Redis, session_id: str, sense_id: int) -> frozenset[int]:
    """Served question ids for a sense — ready to pass to ``resolver.resolve``."""
    members = await redis.smembers(_excluded_key(session_id, sense_id))
    return frozenset(int(member) for member in members)


async def add_excluded(redis: Redis, session_id: str, sense_id: int, question_id: int) -> None:
    key = _excluded_key(session_id, sense_id)
    await redis.sadd(key, question_id)
    await redis.expire(key, _TTL_SECONDS)


# --- consume-once delivered-question bind (F5) ----------------------------------


async def get_delivered(redis: Redis, session_id: str, sense_id: int) -> int | None:
    """The question currently bound to a sense's open checkpoint, if any.

    ``None`` means the checkpoint is open with nothing delivered — which is exactly
    the state ``reserve_round_delivery`` requires before it will serve the sense.
    """
    raw = await redis.hget(_sense_key(session_id, sense_id), "current_qid")
    if raw is None or raw == _MISSING:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def set_delivered(
    redis: Redis, session_id: str, sense_id: int, question_id: int
) -> None:
    """Record the question currently delivered for a sense's open checkpoint."""
    skey = _sense_key(session_id, sense_id)
    await redis.hset(skey, "current_qid", str(question_id))
    await redis.expire(skey, _TTL_SECONDS)


async def consume_delivered(
    redis: Redis, session_id: str, sense_id: int, question_id: int
) -> bool:
    """CAS: consume the delivered question exactly once.

    Returns True only if ``current_qid`` matches ``question_id`` (then clears it);
    a replayed/duplicate/self-selected question id that is not the sense's current
    delivered question is rejected (F5).
    """
    key = _sense_key(session_id, sense_id)
    while True:
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                current = await pipe.hget(key, "current_qid")
                if current is None or current == _MISSING or int(current) != question_id:
                    await pipe.unwatch()
                    return False
                pipe.multi()
                pipe.hset(key, "current_qid", _MISSING)
                pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()
                return True
            except WatchError:
                continue


async def restore_delivered(
    redis: Redis, session_id: str, sense_id: int, question_id: int
) -> None:
    """Reopen a checkpoint after an aborted answer, so the sense stays deliverable.

    This used to re-arm ``current_qid`` with the same question id and stop there,
    which wedged the sense permanently. ``reserve_round_delivery`` refuses any sense
    whose ``current_qid`` is not ``_MISSING``, so once an answer aborted, that sense
    could never be delivered again in any later round — the only escape was the
    client resubmitting the exact same question id. ``/next`` would then keep
    returning "preparing" without ever reaching ``exhausted``.

    Reopening means undoing the whole delivery, not just releasing the claim:

    - clear ``current_qid``, so the sense passes the reservation guard again;
    - move ``last_round_used`` below the current round, so it is eligible again
      immediately rather than only after a round boundary;
    - drop the question id from the exclusion set, so the same checkpoint can be
      re-served rather than forcing a different question.

    ``round_count`` is deliberately NOT decremented. An aborted delivery still
    consumed a slot, so the round may end sooner; that is harmless, because the
    sense is now eligible in the next round rather than stranded. Undoing the
    counter would need its own reconciliation against concurrent reservations for
    no behavioural gain.

    Exposing a resubmit path instead was rejected: it would weaken the consume-once
    tamper protection that ``consume_delivered`` exists to provide.
    """
    meta_key = _key(session_id)
    sense_key = _sense_key(session_id, sense_id)
    excluded_key = _excluded_key(session_id, sense_id)
    while True:
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(meta_key, sense_key)
                raw_round = await pipe.hget(meta_key, "round_index")
                if raw_round is None:
                    # The session is gone (completed or expired); nothing to reopen.
                    await pipe.unwatch()
                    return
                reopened_round = int(raw_round) - 1
                pipe.multi()
                pipe.hset(
                    sense_key,
                    mapping={
                        "current_qid": _MISSING,
                        "last_round_used": str(reopened_round),
                    },
                )
                pipe.srem(excluded_key, question_id)
                pipe.expire(sense_key, _TTL_SECONDS)
                pipe.expire(excluded_key, _TTL_SECONDS)
                await pipe.execute()
                return
            except WatchError:
                continue


async def reopen_bound_delivery(
    redis: Redis, session_id: str, question_id: int
) -> int | None:
    """Reopen whichever sense is currently bound to ``question_id``.

    For rejections raised BEFORE ``consume_delivered``, the caller has no sense id
    — a purged question carries no sense — so the binding is found by scanning the
    admitted set. That is bounded by ``target_words_per_session`` (10 by default),
    not by the deck.

    Guarded on purpose: only the sense actually holding this question id is
    reopened. Reopening grants no progress, but a caller must not be able to reset
    an arbitrary sense's checkpoint by submitting an unrelated question id.

    Returns the sense id reopened, or None when nothing was bound to it.
    """
    for sense_id in await get_admitted(redis, session_id):
        if await get_delivered(redis, session_id, sense_id) == question_id:
            await restore_delivered(redis, session_id, sense_id, question_id)
            return sense_id
    return None


# --- round bookkeeping ----------------------------------------------------------


async def current_round(redis: Redis, session_id: str) -> int:
    raw = await redis.hget(_key(session_id), "round_index")
    return int(raw) if raw is not None else 0


async def advance_round(
    redis: Redis, session_id: str, *, expected_round: int | None = None
) -> int:
    """Atomically advance once from ``expected_round`` and reset round count.

    Returns 0 for a session that no longer exists. HSET creates a missing key, so
    without this guard an expired session was silently resurrected as a hash holding
    nothing but `round_index` — a shape `get_meta` then choked on. The session is
    gone; the honest answer is "no rounds", and the caller's own
    `session_not_found` path handles it.
    """
    key = _key(session_id)
    while True:
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                # `owner` rather than `round_index`: identity is what makes this a
                # session, and it is written once at creation and never removed.
                if not await pipe.hexists(key, "owner"):
                    await pipe.unwatch()
                    return 0
                raw = await pipe.hget(key, "round_index")
                current = int(raw) if raw is not None else 0
                if expected_round is not None and current != expected_round:
                    await pipe.unwatch()
                    return current
                new_index = current + 1
                pipe.multi()
                pipe.hset(key, mapping={"round_index": str(new_index), "round_count": "0"})
                pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()
                return new_index
            except WatchError:
                continue


async def mark_round_used(redis: Redis, session_id: str, sense_id: int, round_index: int) -> None:
    """Record that a sense was served in ``round_index`` (once-per-round guard)."""
    skey = _sense_key(session_id, sense_id)
    await redis.hset(skey, "last_round_used", str(round_index))
    await redis.hincrby(_key(session_id), "round_count", 1)
    await redis.expire(skey, _TTL_SECONDS)


async def set_exposed(redis: Redis, session_id: str, sense_id: int) -> None:
    skey = _sense_key(session_id, sense_id)
    await redis.hset(skey, "exposed", "1")
    await redis.expire(skey, _TTL_SECONDS)


async def set_awaiting_grade(redis: Redis, session_id: str, sense_id: int, on: bool) -> None:
    """Toggle the awaiting-grade flag around a ``pending`` evaluation (F10)."""
    skey = _sense_key(session_id, sense_id)
    await redis.hset(skey, "awaiting_grade", "1" if on else "0")
    await redis.expire(skey, _TTL_SECONDS)


async def mark_fsrs_applied(redis: Redis, session_id: str, sense_id: int) -> None:
    """Best-effort advisory flag; set AFTER the authoritative Postgres commit."""
    skey = _sense_key(session_id, sense_id)
    await redis.hset(skey, "fsrs_applied", "1")
    await redis.expire(skey, _TTL_SECONDS)


# --- atomic (CAS) mutations -----------------------------------------------------


async def apply_checkpoint_projection(
    redis: Redis,
    session_id: str,
    sense_id: int,
    *,
    response_id: UUID,
    state_action: str,
    requested_level: int,
    retries_used: int,
    failed_round: int,
    max_retries: int,
    grade_due: str | None,
    fsrs_applied: bool,
    required_checkpoints: int = REQUIRED_CHECKPOINTS,
) -> bool:
    """Atomically and idempotently project one durable grade into session state."""
    key = _sense_key(session_id, sense_id)
    projected_key = _projected_key(session_id, sense_id)
    projection_id = str(response_id)
    while True:
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key, projected_key)
                raw = await pipe.hgetall(key)
                if not raw:
                    await pipe.unwatch()
                    return False
                if await pipe.sismember(projected_key, projection_id):
                    await pipe.unwatch()
                    return True
                mapping: dict[str, str] = {"awaiting_grade": "0"}
                if state_action == "complete":
                    passed = int(raw["passed"]) + 1
                    mapping.update(
                        passed=str(passed),
                        open_checkpoint=_MISSING,
                        open_requested_level=_MISSING,
                        open_failed_round=_MISSING,
                        retries_used="0",
                    )
                    if passed >= required_checkpoints:
                        mapping.update(terminal="1", terminal_reason="completed")
                else:
                    mapping.update(
                        open_checkpoint=raw["passed"],
                        open_requested_level=str(requested_level),
                        open_failed_round=str(failed_round),
                        retries_used=str(retries_used),
                    )
                    if retries_used > max_retries:
                        mapping.update(terminal="1", terminal_reason="retries_exhausted")
                if grade_due is not None and raw.get("score") == _NONE:
                    mapping["score"] = grade_due
                if fsrs_applied:
                    mapping["fsrs_applied"] = "1"
                pipe.multi()
                pipe.hset(key, mapping=mapping)
                pipe.sadd(projected_key, projection_id)
                pipe.expire(projected_key, _TTL_SECONDS)
                pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()
                return True
            except WatchError:
                continue


async def reserve_round_delivery(
    redis: Redis,
    session_id: str,
    sense_id: int,
    round_index: int,
    *,
    question_id: int | None,
) -> bool:
    """Atomically reserve one sense delivery and account for its round slot."""
    meta_key = _key(session_id)
    sense_key = _sense_key(session_id, sense_id)
    excluded_key = _excluded_key(session_id, sense_id)
    while True:
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(meta_key, sense_key)
                meta = await pipe.hmget(meta_key, "round_index", "round_count", "max_per_round")
                progress = await pipe.hmget(sense_key, "last_round_used", "current_qid")
                if any(value is None for value in (*meta, *progress)):
                    await pipe.unwatch()
                    return False
                current_round, round_count, max_per_round = map(int, meta)
                last_round_used = int(progress[0])
                current_qid = progress[1]
                if (
                    current_round != round_index
                    or round_count >= max_per_round
                    or last_round_used >= round_index
                    or current_qid != _MISSING
                ):
                    await pipe.unwatch()
                    return False
                mapping = {"last_round_used": str(round_index)}
                if question_id is None:
                    mapping["exposed"] = "1"
                else:
                    mapping["current_qid"] = str(question_id)
                pipe.multi()
                pipe.hset(sense_key, mapping=mapping)
                pipe.hincrby(meta_key, "round_count", 1)
                if question_id is not None:
                    pipe.sadd(excluded_key, question_id)
                    pipe.expire(excluded_key, _TTL_SECONDS)
                pipe.expire(sense_key, _TTL_SECONDS)
                pipe.expire(meta_key, _TTL_SECONDS)
                await pipe.execute()
                return True
            except WatchError:
                continue


async def claim_prepare_attempt(
    redis: Redis,
    session_id: str,
    *,
    now_timestamp: float | None = None,
    max_attempts: int = 3,
    retry_delay_seconds: int = 10,
) -> str:
    """Claim a cooldown-bounded supply warm-up attempt.

    Returns ``claimed``, ``waiting``, or ``exhausted``. Supply resolution always
    runs before this gate, so late-arriving questions remain deliverable.
    """
    key = _key(session_id)
    now = datetime.now(UTC).timestamp() if now_timestamp is None else now_timestamp
    while True:
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                raw = await pipe.hmget(key, "prepare_attempts", "prepare_retry_at")
                if raw[0] is None:
                    await pipe.unwatch()
                    return "exhausted"
                attempts = int(raw[0])
                retry_at = float(raw[1] or 0)
                if now < retry_at:
                    await pipe.unwatch()
                    return "waiting"
                if attempts >= max_attempts:
                    await pipe.unwatch()
                    return "exhausted"
                pipe.multi()
                pipe.hset(
                    key,
                    mapping={
                        "prepare_attempts": str(attempts + 1),
                        "prepare_retry_at": str(now + retry_delay_seconds),
                    },
                )
                pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()
                return "claimed"
            except WatchError:
                continue


async def lock_score(redis: Redis, session_id: str, sense_id: int, grade: str) -> str | None:
    """One-shot ``none -> grade`` transition (``grade`` in ``{again, good}``).

    ADVISORY fast-path only (F1): correctness is owned by the Postgres claim in
    Phase 7, committed BEFORE this call.  Returns the applied grade if this call
    won the lock, else ``None`` (already locked or state gone).
    """
    key = _sense_key(session_id, sense_id)
    while True:
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                current = await pipe.hget(key, "score")
                if current is None or current != _NONE:
                    await pipe.unwatch()
                    return None
                pipe.multi()
                pipe.hset(key, "score", grade)
                pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()
                return grade
            except WatchError:
                continue


async def pass_checkpoint(
    redis: Redis,
    session_id: str,
    sense_id: int,
    *,
    required_checkpoints: int = REQUIRED_CHECKPOINTS,
) -> int | None:
    """Increment ``passed``, clear the open checkpoint/retry, reset retry budget.

    Marks the sense terminal (``completed``) when ``passed == N``.  Returns the new
    passed count, or ``None`` when the sense state is gone.
    """
    key = _sense_key(session_id, sense_id)
    while True:
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                raw_passed = await pipe.hget(key, "passed")
                if raw_passed is None:
                    await pipe.unwatch()
                    return None
                new_passed = int(raw_passed) + 1
                mapping = {
                    "passed": str(new_passed),
                    "open_checkpoint": _MISSING,
                    "open_requested_level": _MISSING,
                    "open_failed_round": _MISSING,
                    "retries_used": "0",
                }
                if new_passed >= required_checkpoints:
                    mapping["terminal"] = "1"
                    mapping["terminal_reason"] = "completed"
                pipe.multi()
                pipe.hset(key, mapping=mapping)
                pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()
                return new_passed
            except WatchError:
                continue


async def open_retry(
    redis: Redis,
    session_id: str,
    sense_id: int,
    *,
    requested_level: int,
    retries_used: int,
    failed_round: int,
    max_retries: int = MAX_RETRIES_PER_CHECKPOINT,
) -> None:
    """Open a retry on the current checkpoint (index == ``passed``).

    ``retries_used`` is caller-computed; the sense is marked terminal
    (``retries_exhausted``) when it exceeds ``max_retries``.
    """
    key = _sense_key(session_id, sense_id)
    while True:
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                raw_passed = await pipe.hget(key, "passed")
                if raw_passed is None:
                    await pipe.unwatch()
                    return
                mapping = {
                    "open_checkpoint": raw_passed,
                    "open_requested_level": str(requested_level),
                    "open_failed_round": str(failed_round),
                    "retries_used": str(retries_used),
                }
                if retries_used > max_retries:
                    mapping["terminal"] = "1"
                    mapping["terminal_reason"] = "retries_exhausted"
                pipe.multi()
                pipe.hset(key, mapping=mapping)
                pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()
                return
            except WatchError:
                continue


# --- teardown -------------------------------------------------------------------


async def end_session(redis: Redis, session_id: str) -> None:
    """Delete the whole ``session:{sid}*`` namespace."""
    admitted = await get_admitted(redis, session_id)
    keys = [_key(session_id), _admitted_key(session_id)]
    for sense_id in admitted:
        keys.append(_sense_key(session_id, sense_id))
        keys.append(_excluded_key(session_id, sense_id))
        keys.append(_projected_key(session_id, sense_id))
    if keys:
        await redis.delete(*keys)


# --- quotas (unchanged) ---------------------------------------------------------


# INCR and EXPIRE in one round trip. Done separately, a process that died between
# them left a counter with NO TTL, so the learner's quota key never decayed and they
# were locked out of LLM grading permanently — a durable consequence from a window
# meant to be 5 minutes wide. `jobs/service.py:17-28` already reserves its quota
# through a Lua script for exactly this reason; this brings the learning-side slots
# onto the same footing.
#
# EXPIRE is refreshed on the first increment only, which keeps the window rolling
# from first use rather than sliding forward on every call. Re-arming it every time
# would let a steady stream of requests hold the key open forever.
_TAKE_SLOT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1])) end
return count
"""

# The compensating release for a slot that was taken and then not used. DEL at 1
# rather than DECR to 0, so an unused key disappears instead of lingering with a TTL.
_RELEASE_SLOT = """
local value = tonumber(redis.call('GET', KEYS[1]) or '0')
if value <= 1 then redis.call('DEL', KEYS[1]) else redis.call('DECR', KEYS[1]) end
return 1
"""


async def _take_slot(redis: Redis, key: str, limit: int) -> bool:
    count = await redis.eval(_TAKE_SLOT, 1, key, _GENERATION_QUOTA_WINDOW_SECONDS)
    return int(count) <= limit


async def take_generation_slot(redis: Redis, owner_id: UUID, *, limit: int = 5) -> bool:
    """Bound costly generation scheduling per learner over a short window."""
    return await _take_slot(redis, f"session:generation-quota:{owner_id}", limit)


async def take_grading_slot(redis: Redis, owner_id: UUID, *, limit: int = 20) -> bool:
    """Bound expensive LLM grading per learner over the same short window."""
    return await _take_slot(redis, f"session:grading-quota:{owner_id}", limit)


async def release_grading_slot(redis: Redis, owner_id: UUID) -> None:
    """Give back a grading slot that was taken but never spent.

    The slot is charged before the durable pending row is written, because the
    write is what commits the learner to an LLM call. If that write then fails, the
    learner has paid for a grade that will never happen and cannot retry until the
    window rolls — so the charge has to be undone.

    Best-effort: this runs on an error path, and failing to return a slot must not
    replace the caller's real exception with a Redis one.
    """
    try:
        await redis.eval(_RELEASE_SLOT, 1, f"session:grading-quota:{owner_id}")
    except Exception:
        pass
