from __future__ import annotations

import asyncio

from fastapi import APIRouter

from db.connection import get_connection

router = APIRouter(tags=["opportunities"])

_COLS = [
    "id", "buy_exchange", "sell_exchange", "buy_ask", "sell_bid",
    "gross_spread", "net_spread", "score", "optimal_qty", "status", "detected_at",
]


@router.get("/opportunities")
async def list_opportunities() -> list[dict]:
    def _query() -> list[dict]:
        rows = get_connection().execute("""
            SELECT id, buy_exchange, sell_exchange, buy_ask, sell_bid,
                   gross_spread, net_spread, score, optimal_qty, status, detected_at
            FROM opportunities
            ORDER BY detected_at DESC
            LIMIT 50
        """).fetchall()
        return [dict(zip(_COLS, row)) for row in rows]

    return await asyncio.to_thread(_query)
