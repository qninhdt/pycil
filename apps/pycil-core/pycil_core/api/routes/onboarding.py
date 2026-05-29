"""First-login onboarding endpoint.

Single POST /onboarding/seed — idempotent. Web layer fires this on the first
dashboard load; subsequent calls early-return False because the user already
has nodes.
"""
from __future__ import annotations

from fastapi import APIRouter

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.services import onboarding_service

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/seed")
async def seed(user: UserDep, session: SessionDep) -> dict:
    seeded = await onboarding_service.seed_sample(session, user.id)
    return {"seeded": seeded}
