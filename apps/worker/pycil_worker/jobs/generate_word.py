"""generate_word: lazy dictionary generation (single-writer — worker only).

lexi-ai persists the entry to ITS OWN database and returns sense ids. pycil
stores no dictionary content. Guards an empty search by falling back to the
custom-string generate path.
"""

from pycil_worker import realtime


async def generate_word(ctx: dict, owner_uid: str, query: str) -> dict:
    client = ctx["lexi_client"]
    job_id = ctx["job_id"]

    await realtime.publish_job(owner_uid, job_id, "running")

    results = await client.search(query)
    # Empty-search guard: no Cambridge/generated hit → custom-string generate.
    source = results[0] if results else query
    entry = await client.generate(source)

    sense_ids = [s.sense_id for s in entry.senses if s.sense_id is not None]
    await realtime.publish_job(owner_uid, job_id, "done", detail=entry.display)
    # pycil stores nothing here — the ids belong to lexi's DB.
    return {"status": "done", "word_id": entry.word_id, "sense_ids": sense_ids}
