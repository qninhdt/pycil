"""Word effects use Lexi's dictionary identity and fenced generation with Redis Singleflight."""

from pycil.jobs.contracts import WordDispatch
from pycil.jobs.deduplication import singleflight_generate_word
from pycil.worker.context import WorkerContext


async def generate_word(ctx: WorkerContext, dispatch: dict) -> dict:
    payload = WordDispatch.from_dispatch(dispatch)

    async def _do_generate() -> dict:
        results = await ctx["lexi_reader"].search(payload.query)
        entry = await ctx["lexi_engine"].generate_fenced(results[0] if results else payload.query)
        return {
            "wordId": entry.word_id,
            "senseIds": [sense.sense_id for sense in entry.senses if sense.sense_id is not None],
        }

    async def _fetch_existing() -> dict:
        results = await ctx["lexi_reader"].search(payload.query)
        if results:
            entry = results[0]
            return {
                "wordId": entry.word_id,
                "senseIds": [
                    sense.sense_id for sense in entry.senses if sense.sense_id is not None
                ],
            }
        return {"wordId": 0, "senseIds": []}

    return await singleflight_generate_word(
        redis=ctx["redis"],
        query=payload.query,
        generate_fn=_do_generate,
        fetch_existing_fn=_fetch_existing,
    )
