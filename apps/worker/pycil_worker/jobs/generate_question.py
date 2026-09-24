"""Prepare supply; Lexi's content-hash unique key deduplicates repeated writes."""

from collections import defaultdict

from lexi_ai.contracts import PrepareDemand
from pycil.queue.contracts import SupplyDispatch

from pycil_worker.context import ReadyWorkerContext


async def prepare_questions(ctx: ReadyWorkerContext, dispatch: dict) -> dict:
    payload = SupplyDispatch.from_dispatch(dispatch)
    by_word: dict[int, list[PrepareDemand]] = defaultdict(list)
    for sense_id, level in payload.demands:
        word_id = await ctx["lexi_reader"].word_id_for(sense_id)
        if word_id is None:
            continue
        by_word[word_id].append(PrepareDemand(sense_id=sense_id, difficulty_level=level))
    prepared = 0
    for word_id, demands in by_word.items():
        report = await ctx["lexi_engine"].prepare_questions(word_id, demands)
        if any(
            report.produced.get((demand.sense_id, demand.difficulty_level), 0) <= 0
            for demand in demands
        ):
            # Lexi logs plugin failures and returns zero. The durable attempt
            # bound must own recovery instead of reporting missing supply as success.
            raise RuntimeError("question_supply_unavailable")
        prepared += sum(report.produced.values())
    return {"prepared": prepared}
