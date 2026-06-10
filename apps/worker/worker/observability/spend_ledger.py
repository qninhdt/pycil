"""Best-effort persistent LLM spend ledger writer.

Writes one `llm_spend_events` row per non-cached LLM call. CRITICAL (red-team
F1): this opens its OWN short-lived session — it must NEVER receive the job's
`AsyncSession`. A failed insert leaves an async session in pending-rollback;
reusing the generation session would then raise `PendingRollbackError` on the
next ORM op and roll back generation that already succeeded.

Any exception is logged (`spend_ledger_write_failed`) and swallowed so
generation always continues. Idempotent on `job_id` (ON CONFLICT DO NOTHING) so
an arq retry that re-invokes the model does not double-count.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text

from worker.db import SessionLocal

_log = logging.getLogger(__name__)


async def record_spend_event(
    *,
    user_id: str | UUID | None,
    job_id: str | UUID | None,
    job_type: str,
    model: str,
    cost_usd: float,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> None:
    """Insert a spend row in a DEDICATED session. Best-effort; never raises."""
    try:
        async with SessionLocal() as ledger_session:
            await ledger_session.execute(
                text(
                    """
                    INSERT INTO llm_spend_events (
                        user_id, job_id, job_type, model, cost_usd,
                        input_tokens, output_tokens
                    )
                    VALUES (
                        CAST(:user_id AS uuid), CAST(:job_id AS uuid),
                        :job_type, :model, :cost_usd, :input_tokens, :output_tokens
                    )
                    ON CONFLICT (job_id) DO NOTHING
                    """
                ),
                {
                    "user_id": str(user_id) if user_id else None,
                    "job_id": str(job_id) if job_id else None,
                    "job_type": job_type,
                    "model": model,
                    "cost_usd": cost_usd,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            )
            await ledger_session.commit()
    except Exception as exc:  # noqa: BLE001
        _log.warning("spend_ledger_write_failed", extra={"err": str(exc)[:300]})
