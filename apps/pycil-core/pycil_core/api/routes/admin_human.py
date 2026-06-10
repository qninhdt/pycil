"""Human-facing admin API, gated by `AdminDep` (authoritative DB role read).

Mounted under `/admin-api/*` (NOT `/admin/*`). Rationale (red-team F1/F2):
- `Caddyfile` hard-404s `/api/core/admin/*` and the internal-secret router
  (`admin.py`) already lives under `/admin`. Browser-facing admin routes must
  therefore live under `/admin-api`, which the catch-all `handle_path
  /api/core/*` forwards untouched. FE base URL is `/api/core`, so calls land at
  `/api/core/admin-api/*`.

Phase 1 ships only `/admin-api/ping` (the load-bearing gate smoke route).
Later phases mount users / reports / metrics / flags / health / audit routers.
"""
from __future__ import annotations

from fastapi import APIRouter

from pycil_core.api.deps import AdminDep

router = APIRouter(prefix="/admin-api", tags=["admin-human"])


@router.get("/ping")
async def ping(user: AdminDep) -> dict:
    """Admin-gated liveness check. Returns 403 for non-admins."""
    return {"ok": True, "admin_id": str(user.id)}
