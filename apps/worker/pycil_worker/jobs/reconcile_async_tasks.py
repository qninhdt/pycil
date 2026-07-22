"""Restore durable task rows when their initial ARQ enqueue did not persist."""


async def reconcile_async_tasks(ctx: dict) -> dict:
    from pycil.tasks import service as task_service

    async with ctx["session_factory"]() as session:
        tasks = await task_service.list_reenqueueable_tasks(session)

    for task in tasks:
        dispatch = task.result["dispatch"]
        if task.kind == "word":
            await ctx["redis"].enqueue_job("generate_word_task", str(task.id), dispatch["query"])
        elif task.kind == "question_pool":
            await ctx["redis"].enqueue_job(
                "generate_question",
                str(task.id),
                dispatch["word_id"],
                dispatch["formats"],
                dispatch["n"],
                None,
                dispatch["sense_id"],
            )
        elif task.kind == "grading":
            await ctx["redis"].enqueue_job(
                "grade_answer_task", str(task.id), dispatch["owner_id"], dispatch["response_id"]
            )
    return {"status": "reconciled", "count": len(tasks)}
