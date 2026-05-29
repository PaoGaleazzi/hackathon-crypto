from __future__ import annotations

from fastapi import APIRouter

from core.triangular import get_latest_opportunities, triangular_to_dict

router = APIRouter(tags=["triangular"])


@router.get("/triangular")
async def list_triangular() -> list[dict]:
    """Latest triangular arbitrage opportunities detected by the pipeline.

    Served from the in-memory cache (no DuckDB), refreshed every tick.
    """
    return [triangular_to_dict(opp) for opp in get_latest_opportunities()]
