"""generate_question: delegate question generation to lexi-ai's QuestionEngine.

Questions are generated + persisted inside lexi-ai's DB (via the port, which
routes to ``lexicon.questions``). The worker publishes the resulting question
ids/payloads to the owner-scoped channel.
"""

from pycil_worker import realtime


async def generate_question(
    ctx: dict, owner_uid: str, word_id: int, formats: list[str], n: int = 1
) -> dict:
    client = ctx["lexi_client"]
    job_id = ctx["job_id"]

    await realtime.publish_job(owner_uid, job_id, "running")

    entry = await client.get(word_id) if hasattr(client, "get") else None
    if entry is None:
        # The port exposes generate/search/get_senses; fetch the entry via the
        # underlying lexicon for question context.
        entry = await ctx["lexicon"].get(word_id)

    questions = await client.generate_questions(entry, formats, n)
    payloads = [
        {"id": q.id, "sense_id": q.sense_id, "format": q.format, "payload": q.payload}
        for q in questions
    ]
    await realtime.publish_job(owner_uid, job_id, "done")
    return {"status": "done", "questions": payloads}
