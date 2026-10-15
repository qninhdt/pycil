import gzip
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import cast

from sqlalchemy import CursorResult, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.infrastructure.database import transaction_lock
from pycil.infrastructure.observability import get_logger
from pycil.vocabulary.references.models import ReferenceSense, ReferenceWord, SourceWord

logger = get_logger(__name__)


async def _insert_identical(
    session: AsyncSession,
    model: type[ReferenceWord] | type[ReferenceSense],
    rows: list[dict[str, object]],
) -> None:
    table = model.__table__
    result = await session.execute(
        insert(model).values(rows).on_conflict_do_nothing(index_elements=["id"])
    )
    cursor_result = cast(CursorResult[object], result)
    if cursor_result.rowcount < len(rows):
        stored = {
            row["id"]: dict(row)
            for row in (
                await session.execute(
                    select(table).where(table.c.id.in_([row["id"] for row in rows]))
                )
            ).mappings()
        }
        if any(stored.get(row["id"]) != row for row in rows):
            raise ValueError("reference identity conflicts with existing content")


async def import_reference(
    sessions: async_sessionmaker[AsyncSession], path: Path
) -> dict[str, int | str]:
    """One transaction: readers see either the previous dataset or the complete import."""
    started = perf_counter()
    digest = sha256()
    seen_words: set[int] = set()
    seen_senses: set[int] = set()
    words: list[dict[str, object]] = []
    senses: list[dict[str, object]] = []

    async def flush(session: AsyncSession) -> None:
        if words:
            await _insert_identical(session, ReferenceWord, words)
            await _insert_identical(session, ReferenceSense, senses)
            words.clear()
            senses.clear()

    logger.info("reference_import_started", artifact=path.name)
    try:
        async with sessions() as session, session.begin():
            await transaction_lock(session, "reference_import")
            stream = gzip.open(path, "rb") if path.suffix == ".gz" else path.open("rb")
            with stream as source:
                for number, line in enumerate(source, 1):
                    digest.update(line)
                    if not line.strip():
                        continue
                    try:
                        word = SourceWord.model_validate_json(line)
                    except ValueError:
                        raise ValueError(f"invalid reference record at line {number}") from None
                    if word.id in seen_words or any(s.id in seen_senses for s in word.senses):
                        raise ValueError(f"duplicate reference identity at line {number}")
                    seen_words.add(word.id)
                    seen_senses.update(s.id for s in word.senses)
                    payload = word.model_dump(mode="json", exclude={"senses"})
                    words.append(payload)
                    senses.extend({"word_id": word.id, **s.model_dump()} for s in word.senses)
                    # Keep the widest batch below the async driver's bind parameter limit.
                    if len(senses) >= 1000 or len(words) >= 500:
                        await flush(session)
            if not seen_words:
                raise ValueError("reference artifact has no words")
            await flush(session)
    except BaseException as error:
        logger.warning(
            "reference_import_failed",
            artifact=path.name,
            error_type=type(error).__name__,
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )
        raise
    result = {"words": len(seen_words), "senses": len(seen_senses), "checksum": digest.hexdigest()}
    logger.info(
        "reference_import_completed",
        artifact=path.name,
        duration_ms=round((perf_counter() - started) * 1000, 2),
        **result,
    )
    return result
