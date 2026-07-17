"""Expire pending assistant approvals without racing a user confirmation."""

from pycil.assistant.hitl import expire_pending_actions


async def reconcile_expired_assistant_actions(ctx: dict) -> int:
    async with ctx["session_factory"]() as session:
        return await expire_pending_actions(session)
