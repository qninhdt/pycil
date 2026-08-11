"""Expire pending assistant approvals without racing a user confirmation."""

from pycil.assistant.application.hitl import expire_pending_actions

from pycil_worker.context import ReadyWorkerContext


async def reconcile_expired_assistant_actions(ctx: ReadyWorkerContext) -> int:
    async with ctx["session_factory"]() as session:
        return await expire_pending_actions(session)
