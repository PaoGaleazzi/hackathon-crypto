from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from core.circuit_breaker import get_circuit_breaker

router = APIRouter(prefix="/circuit-breaker", tags=["circuit-breaker"])


@router.get("")
async def get_status() -> dict:
    cb = get_circuit_breaker()
    now = datetime.now(timezone.utc)
    return cb.as_dict(now)


@router.post("/reset")
async def reset() -> dict:
    """Force circuit breaker to CLOSED. Clears all counters."""
    cb = get_circuit_breaker()
    cb._close()
    return cb.as_dict()


@router.post("/open")
async def force_open() -> dict:
    """Force circuit breaker to OPEN. Use in demo to show safety mechanism."""
    cb = get_circuit_breaker()
    now = datetime.now(timezone.utc)
    cb._open(now, reason="manual")
    return cb.as_dict(now)
