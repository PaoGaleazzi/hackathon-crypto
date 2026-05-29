from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from config import settings
from core.circuit_breaker import get_circuit_breaker

router = APIRouter(tags=["health"])


@router.get("/health")
async def get_health() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "status": "ok",
        "timestamp": now.isoformat(),
        "version": settings.version,
        "circuit_breaker": get_circuit_breaker().as_dict(now=now),
    }
