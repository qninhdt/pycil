"""Redis Single Document study session store.

Replaces fragmented Redis keys with a single JSON document per study session
safeguarded by atomic optimistic locking.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from redis.asyncio import Redis

from pycil.common.errors import ConflictError
from pycil.learning.session_doc import SenseProgressDoc, StudySessionDoc
from pycil.product_config import system_config


def _ttl_seconds() -> int:
    """Session lifetime, owned by ``config/config.yaml``.

    Read through a function so importing this module does not parse the config
    file, and so the TTL is the same value every caller sees.
    """
    return system_config.learning.session_ttl_seconds


# The TTL is passed in as an argument rather than interpolated into the script:
# a literal inside the Lua body would not follow the configured value, which is
# how the two drifted apart before.
_SAVE_LUA = """
local current = redis.call('get', KEYS[1])
if not current then
    return 0
end
local doc = cjson.decode(current)
if doc['version'] == tonumber(ARGV[2]) then
    redis.call('set', KEYS[1], ARGV[1], 'EX', tonumber(ARGV[3]))
    return 1
else
    return 0
end
"""


@dataclass(frozen=True)
class SessionMeta:
    owner_id: UUID
    node_id: UUID
    scope_generation: int
    round_index: int
    round_count: int
    target_words: int
    max_per_round: int
    new_count: int
    failed_count: int
    items_served: int
    expires_at: datetime


@dataclass(frozen=True)
class AdmittedSense:
    sense_id: int
    purpose: str  # "due" | "new"
    requested_level: int


@dataclass
class SenseProgress:
    sense_id: int
    exposed: bool
    last_round_used: int
    current_qid: int | None
    current_kind: str
    delivery_round: int | None
    delivery_id: UUID | None
    requested_level: int
    reask_pending: bool
    reask_level: int | None
    reask_failed_round: int | None
    reask_done: bool
    terminal: bool
    terminal_reason: str
    failed_count: int


@dataclass(frozen=True)
class Delivery:
    question_id: int | None
    kind: str
    round_index: int
    delivery_id: UUID | None


def _to_session_meta(doc: StudySessionDoc) -> SessionMeta:
    return SessionMeta(
        owner_id=doc.owner_id,
        node_id=doc.node_id,
        scope_generation=doc.scope_generation,
        round_index=doc.round_index,
        round_count=doc.round_count,
        target_words=doc.target_words,
        max_per_round=doc.max_per_round,
        new_count=doc.new_count,
        failed_count=doc.failed_count,
        items_served=doc.items_served,
        expires_at=doc.expires_at,
    )


def _to_sense_progress(p: SenseProgressDoc) -> SenseProgress:
    return SenseProgress(
        sense_id=p.sense_id,
        exposed=p.exposed,
        last_round_used=p.last_round_used,
        current_qid=p.current_qid,
        current_kind=p.current_kind,
        delivery_round=p.delivery_round,
        delivery_id=p.delivery_id,
        requested_level=p.requested_level,
        reask_pending=p.reask_pending,
        reask_level=p.reask_level,
        reask_failed_round=p.reask_failed_round,
        reask_done=p.reask_done,
        terminal=p.terminal,
        terminal_reason=p.terminal_reason,
        failed_count=p.failed_count,
    )


def _key(session_id: str) -> str:
    return f"pycil:session:{session_id}"


async def _mutate(
    redis: Redis, session_id: str, mutate_fn: Callable[[StudySessionDoc], Any]
) -> Any:
    key = _key(session_id)
    raw = await redis.get(key)
    if not raw:
        return None
    doc = StudySessionDoc.model_validate_json(raw)
    if doc.schema_version != 1:
        raise ConflictError("study_session_schema_unsupported")
    expected_version = doc.version
    doc.version += 1
    res = mutate_fn(doc)
    if res is False:
        return False
    ttl = int((doc.expires_at - datetime.now(UTC)).total_seconds())
    if ttl <= 0:
        await redis.delete(key)
        return None
    saved = await redis.eval(
        _SAVE_LUA, 1, key, doc.model_dump_json(), expected_version, ttl
    )
    if saved != 1:
        raise ConflictError("study_session_changed")
    return res


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
    expires_at = (datetime.now(UTC) + timedelta(seconds=_ttl_seconds())).replace(microsecond=0)
    new_count = sum(item.purpose == "new" for item in admitted)

    progress_map: dict[int, SenseProgressDoc] = {}
    admitted_map: dict[int, str] = {}
    for item in admitted:
        admitted_map[item.sense_id] = item.purpose
        progress_map[item.sense_id] = SenseProgressDoc(
            sense_id=item.sense_id,
            requested_level=item.requested_level,
        )

    doc = StudySessionDoc(
        session_id=session_id,
        owner_id=owner_id,
        node_id=node_id,
        scope_generation=scope_generation,
        version=1,
        target_words=target_words,
        max_per_round=max_per_round,
        new_count=new_count,
        expires_at=expires_at,
        admitted=admitted_map,
        progress=progress_map,
    )
    raw = doc.model_dump_json()
    await redis.set(_key(session_id), raw, ex=max(1, _ttl_seconds()))
    return _to_session_meta(doc)


async def get_meta(redis: Redis, session_id: str) -> SessionMeta | None:
    raw = await redis.get(_key(session_id))
    if not raw:
        return None
    doc = StudySessionDoc.model_validate_json(raw)
    return _to_session_meta(doc)


async def get_admitted(redis: Redis, session_id: str) -> dict[int, str]:
    raw = await redis.get(_key(session_id))
    if not raw:
        return {}
    doc = StudySessionDoc.model_validate_json(raw)
    return doc.admitted


async def get_progress(redis: Redis, session_id: str, sense_id: int) -> SenseProgress | None:
    raw = await redis.get(_key(session_id))
    if not raw:
        return None
    doc = StudySessionDoc.model_validate_json(raw)
    p = doc.progress.get(sense_id)
    return _to_sense_progress(p) if p else None


async def graded_senses(redis: Redis, session_id: str) -> frozenset[int]:
    raw = await redis.get(_key(session_id))
    if not raw:
        return frozenset()
    doc = StudySessionDoc.model_validate_json(raw)
    return frozenset(doc.graded)


async def is_graded(redis: Redis, session_id: str, sense_id: int) -> bool:
    raw = await redis.get(_key(session_id))
    if not raw:
        return False
    doc = StudySessionDoc.model_validate_json(raw)
    return sense_id in doc.graded


async def excluded_ids(redis: Redis, session_id: str, sense_id: int) -> frozenset[int]:
    raw = await redis.get(_key(session_id))
    if not raw:
        return frozenset()
    doc = StudySessionDoc.model_validate_json(raw)
    return frozenset(doc.excluded.get(sense_id, []))


async def get_delivery(redis: Redis, session_id: str, sense_id: int) -> Delivery | None:
    progress = await get_progress(redis, session_id, sense_id)
    if progress is None or not progress.current_kind or progress.delivery_round is None:
        return None
    delivery_id = progress.delivery_id
    if delivery_id is None and progress.current_qid is not None:
        # Older live documents predate `delivery_id`; derive a stable id from the
        # issued delivery so a re-ask can still be charged once during the TTL.
        delivery_id = uuid5(
            NAMESPACE_URL,
            f"pycil:{session_id}:{sense_id}:{progress.current_qid}:{progress.delivery_round}",
        )
    return Delivery(
        progress.current_qid,
        progress.current_kind,
        progress.delivery_round,
        delivery_id,
    )


async def set_delivered(
    redis: Redis,
    session_id: str,
    sense_id: int,
    question_id: int,
    *,
    kind: str = "grade",
    round_index: int | None = None,
) -> None:
    def _apply(doc: StudySessionDoc):
        p = doc.progress.setdefault(sense_id, SenseProgressDoc(sense_id=sense_id))
        p.current_qid = question_id
        p.current_kind = kind
        p.claim_token = None
        p.claim_expires_at = None
        p.delivery_id = uuid4()
        if round_index is not None:
            p.delivery_round = round_index
        return True

    await _mutate(redis, session_id, _apply)


async def consume_delivered(
    redis: Redis, session_id: str, sense_id: int, question_id: int
) -> bool:
    def _apply(doc: StudySessionDoc):
        p = doc.progress.get(sense_id)
        if not p or p.current_qid != question_id:
            return False
        p.current_qid = None
        p.current_kind = ""
        p.delivery_round = None
        p.delivery_id = None
        p.claim_token = None
        p.claim_expires_at = None
        return True

    res = await _mutate(redis, session_id, _apply)
    return bool(res)


async def restore_delivered(
    redis: Redis, session_id: str, sense_id: int, question_id: int
) -> None:
    def _apply(doc: StudySessionDoc):
        p = doc.progress.get(sense_id)
        if not p or p.current_qid != question_id:
            return False
        p.current_qid = None
        p.current_kind = ""
        p.delivery_round = None
        p.delivery_id = None
        p.claim_token = None
        p.claim_expires_at = None
        p.last_round_used = max(-1, doc.round_index - 1)
        if sense_id in doc.excluded and question_id in doc.excluded[sense_id]:
            doc.excluded[sense_id].remove(question_id)
        return True

    await _mutate(redis, session_id, _apply)


async def restore_consumed_delivery(
    redis: Redis,
    session_id: str,
    sense_id: int,
    question_id: int,
    *,
    kind: str,
    round_index: int,
) -> None:
    def _apply(doc: StudySessionDoc):
        p = doc.progress.setdefault(sense_id, SenseProgressDoc(sense_id=sense_id))
        p.current_qid = question_id
        p.current_kind = kind
        p.delivery_round = round_index
        p.delivery_id = uuid4()
        p.claim_token = None
        p.claim_expires_at = None
        return True

    await _mutate(redis, session_id, _apply)


async def reopen_bound_delivery(redis: Redis, session_id: str, question_id: int) -> int | None:
    raw = await redis.get(_key(session_id))
    if not raw:
        return None
    doc = StudySessionDoc.model_validate_json(raw)
    for sense_id, p in doc.progress.items():
        if p.current_qid == question_id:
            await restore_delivered(redis, session_id, sense_id, question_id)
            return sense_id
    return None


async def current_round(redis: Redis, session_id: str) -> int:
    raw = await redis.get(_key(session_id))
    if not raw:
        return 0
    doc = StudySessionDoc.model_validate_json(raw)
    return doc.round_index


_SUBMISSION_CLAIM_SECONDS = 30


async def claim_delivery(
    redis: Redis,
    session_id: str,
    sense_id: int,
    question_id: int,
    *,
    now: datetime | None = None,
) -> str | None:
    """Claim one issued assessment for a bounded grading attempt."""
    moment = now if now is not None else datetime.now(UTC)
    token = uuid4().hex

    def _apply(doc: StudySessionDoc):
        progress = doc.progress.get(sense_id)
        if (
            progress is None
            or progress.current_qid != question_id
            or progress.current_kind not in {"grade", "reask"}
        ):
            return False
        if (
            progress.claim_token is not None
            and progress.claim_expires_at is not None
            and progress.claim_expires_at > moment
        ):
            return False
        progress.claim_token = token
        progress.claim_expires_at = moment + timedelta(seconds=_SUBMISSION_CLAIM_SECONDS)
        return token

    result = await _mutate(redis, session_id, _apply)
    return result if isinstance(result, str) else None


async def release_delivery_claim(
    redis: Redis,
    session_id: str,
    sense_id: int,
    question_id: int,
    claim_token: str,
) -> bool:
    """Release a claim only while the same request still owns the delivery."""

    def _apply(doc: StudySessionDoc):
        progress = doc.progress.get(sense_id)
        if (
            progress is None
            or progress.current_qid != question_id
            or progress.claim_token != claim_token
        ):
            return False
        progress.claim_token = None
        progress.claim_expires_at = None
        return True

    try:
        return bool(await _mutate(redis, session_id, _apply))
    except ConflictError as error:
        if error.code == "study_session_changed":
            return False
        raise


async def advance_round(
    redis: Redis, session_id: str, *, expected_round: int | None = None
) -> int:
    def _apply(doc: StudySessionDoc):
        if expected_round is not None and doc.round_index != expected_round:
            return doc.round_index
        doc.round_index += 1
        doc.round_count = 0
        return doc.round_index

    res = await _mutate(redis, session_id, _apply)
    return res if res is not None else 0


async def apply_grade_projection(
    redis: Redis,
    session_id: str,
    sense_id: int,
    *,
    response_id: UUID,
    served_level: int,
    correct: bool,
    failed_round: int,
    claim_token: str | None = None,
) -> bool:
    del response_id

    def _apply(doc: StudySessionDoc):
        if sense_id in doc.graded:
            return True
        p = doc.progress.setdefault(sense_id, SenseProgressDoc(sense_id=sense_id))
        if claim_token is not None and p.claim_token != claim_token:
            return False
        p.current_qid = None
        p.current_kind = ""
        p.delivery_round = None
        p.delivery_id = None
        p.claim_token = None
        p.claim_expires_at = None

        if correct:
            p.terminal = True
            p.terminal_reason = "completed"
            p.reask_pending = False
            p.reask_done = False
            p.reask_level = None
            p.reask_failed_round = None
        else:
            p.terminal = False
            p.terminal_reason = ""
            p.reask_pending = True
            p.reask_done = False
            p.reask_level = served_level
            p.reask_failed_round = failed_round
            p.failed_count += 1
            doc.failed_count += 1

        doc.graded.append(sense_id)
        return True

    res = await _mutate(redis, session_id, _apply)
    return bool(res)


async def complete_reask(
    redis: Redis,
    session_id: str,
    sense_id: int,
    *,
    claim_token: str | None = None,
) -> bool:
    def _apply(doc: StudySessionDoc):
        p = doc.progress.get(sense_id)
        if not p or not p.reask_pending or p.reask_done:
            return False
        if claim_token is not None and p.claim_token != claim_token:
            return False
        p.current_qid = None
        p.current_kind = ""
        p.delivery_round = None
        p.delivery_id = None
        p.claim_token = None
        p.claim_expires_at = None
        p.reask_pending = False
        p.reask_done = True
        p.terminal = True
        p.terminal_reason = "completed"
        return True

    res = await _mutate(redis, session_id, _apply)
    return bool(res)


async def reserve_round_delivery(
    redis: Redis,
    session_id: str,
    sense_id: int,
    round_index: int,
    *,
    question_id: int | None,
    kind: str = "grade",
) -> bool:
    if kind not in {"exposure", "grade", "reask"}:
        raise ValueError(f"unknown delivery kind: {kind}")

    def _apply(doc: StudySessionDoc):
        p = doc.progress.get(sense_id)
        if not p:
            return False
        if doc.round_index != round_index:
            return False
        if doc.round_count >= doc.max_per_round:
            return False
        if p.last_round_used >= round_index:
            return False
        if p.current_qid is not None:
            return False

        if kind == "exposure":
            p.exposed = True
        p.last_round_used = round_index
        p.current_qid = question_id
        p.current_kind = kind
        p.delivery_round = round_index
        p.delivery_id = uuid4()
        p.claim_token = None
        p.claim_expires_at = None

        doc.round_count += 1
        doc.items_served += 1
        if question_id is not None:
            doc.excluded.setdefault(sense_id, []).append(question_id)
        return True

    res = await _mutate(redis, session_id, _apply)
    return bool(res)


async def claim_prepare_attempt(
    redis: Redis,
    session_id: str,
    *,
    now_timestamp: float | None = None,
    max_attempts: int = 3,
    retry_delay_seconds: int = 10,
) -> str:
    now = datetime.now(UTC).timestamp() if now_timestamp is None else now_timestamp

    def _apply(doc: StudySessionDoc):
        if now < doc.prepare_retry_at:
            return "waiting"
        if doc.prepare_attempts >= max_attempts:
            return "exhausted"
        doc.prepare_attempts += 1
        doc.prepare_retry_at = now + retry_delay_seconds
        return "claimed"

    try:
        res = await _mutate(redis, session_id, _apply)
    except ConflictError as error:
        if error.code == "study_session_changed":
            return "waiting"
        raise
    return res if res is not None else "exhausted"


async def end_session(redis: Redis, session_id: str) -> None:
    await redis.delete(_key(session_id))
