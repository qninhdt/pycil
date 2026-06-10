"""Admin metrics dashboard route (Phase 4), gated by `AdminDep`.

Assembles `product_metrics_service.snapshot()` + signup funnel + the Phase 3
spend ledger aggregations. Read-only, all pure SELECT. Spend figures are
ESTIMATED (flat per-call constant) — the UI labels them so.

Mounts under `/admin-api/metrics`.
"""
from __future__ import annotations

import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter

from pycil_core.api.deps import AdminDep, SessionDep
from pycil_core.services import product_metrics_service, spend_ledger_service

router = APIRouter(prefix="/admin-api/metrics", tags=["admin-metrics"])

# Tiny in-process snapshot cache so a dashboard refresh doesn't recompute the
# DAU/WAU scans every time. 30s TTL; single-operator tool, process-local is fine.
_SNAPSHOT_TTL_SECONDS = 30.0
_snapshot_at: float = 0.0
_snapshot_value: dict | None = None


async def _cached_snapshot(session) -> dict:
    global _snapshot_at, _snapshot_value
    now = time.monotonic()
    if _snapshot_value is not None and now - _snapshot_at < _SNAPSHOT_TTL_SECONDS:
        return _snapshot_value
    snap = await product_metrics_service.snapshot(session)
    _snapshot_value = asdict(snap)
    _snapshot_at = now
    return _snapshot_value


@router.get("")
async def metrics(
    admin: AdminDep,
    session: SessionDep,
    days: int = 30,
) -> dict:
    days = min(max(days, 1), 365)
    end = datetime.now(UTC)
    start = end - timedelta(days=days)

    snapshot = await _cached_snapshot(session)
    funnel = await product_metrics_service.signup_funnel(
        session, start=start, end=end
    )
    spend_by_day = await spend_ledger_service.spend_by_day(
        session, start=start, end=end
    )
    spend_by_model = await spend_ledger_service.spend_by_model(
        session, start=start, end=end
    )
    top_spenders = await spend_ledger_service.top_spenders(
        session, start=start, end=end, limit=10
    )

    return {
        "range_days": days,
        "snapshot": snapshot,
        "signup_funnel": funnel,
        "spend_by_day": spend_by_day,
        "spend_by_model": spend_by_model,
        "top_spenders": top_spenders,
        "spend_estimated": True,
    }
