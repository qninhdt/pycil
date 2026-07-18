"""Re-enqueue durable word jobs left queued during a Redis/API outage."""


async def reconcile_queued_word_generations(ctx: dict) -> dict:
    from pycil.jobs import service as jobs_service

    session_factory = ctx["session_factory"]
    redis = ctx["redis"]
    async with session_factory() as session:
        queued = await jobs_service.list_queued_generations(session)

    for record in queued:
        await redis.enqueue_job(
            "generate_word", str(record.owner_id), record.query, str(record.id)
        )
    return {"status": "reconciled", "count": len(queued)}
