"""HTTP route modules for the HeardIt API."""

from fastapi import APIRouter

from app.routers.heardit import router as heardit_router

router = APIRouter()
router.include_router(heardit_router)

__all__ = ["router"]
