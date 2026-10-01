"""Library HTTP surface composed from focused route groups."""

from fastapi import APIRouter

from pycil.library.membership_api import router as membership_router
from pycil.library.nodes_api import router as nodes_router

router = APIRouter()
router.include_router(nodes_router)
router.include_router(membership_router)

__all__ = ["router"]
