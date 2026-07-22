"""Health endpoints — required by Railway deploy principles (PRD §4.2)."""

from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness: process is up."""
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict:
    """Readiness: DB reachable."""
    from packages.core.db.session import get_session_factory

    try:
        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready", "db": "ok"}
    except Exception as exc:  # pragma: no cover - infra dependent
        return {"status": "degraded", "db": str(exc.__class__.__name__)}
