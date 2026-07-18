"""generate_word: lazy dictionary generation (single-writer — worker only).

lexi-ai persists the entry to ITS OWN database and returns sense ids. pycil
stores no dictionary content. Guards an empty search by falling back to the
custom-string generate path.
"""

from uuid import UUID

from pycil_worker import realtime


async def generate_word(ctx: dict, owner_uid: str, query: str, generation_id: str) -> dict:
    client = ctx["lexi_client"]
    session_factory = ctx["session_factory"]

    from pycil.jobs import service as jobs_service

    async with session_factory() as session:
        record = await jobs_service.mark_running(session, UUID(generation_id))
    if record is None:
        return {"status": "duplicate"}

    await realtime.publish_job(owner_uid, generation_id, "running")

    try:
        results = await client.search(query)
        # Empty-search guard: no Cambridge/generated hit → custom-string generate.
        source = results[0] if results else query
        entry = await client.generate(source)
    except Exception:
        async with session_factory() as session:
            await jobs_service.mark_failed(session, UUID(generation_id), "generation_failed")
        await realtime.publish_job(owner_uid, generation_id, "failed")
        raise

    sense_ids = [s.sense_id for s in entry.senses if s.sense_id is not None]
    result = {"wordId": entry.word_id, "senseIds": sense_ids}
    async with session_factory() as session:
        await jobs_service.mark_succeeded(session, UUID(generation_id), result)
    await realtime.publish_job(owner_uid, generation_id, "succeeded", detail=entry.display)
    # pycil stores nothing here — the ids belong to lexi's DB.
    return {"status": "succeeded", **result}
