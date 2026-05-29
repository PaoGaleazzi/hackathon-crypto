from __future__ import annotations

import asyncio

from fastapi import APIRouter

from core.liquidity_health import get_liquidity_monitor
from db.connection import get_connection
from models.market import Exchange

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
        monitor = get_liquidity_monitor()
        result = []
        for row in rows:
            d = dict(zip(_COLS, row))
            buy_ex = Exchange(d["buy_exchange"])
            sell_ex = Exchange(d["sell_exchange"])
            d["degraded_liquidity"] = (
                not monitor.is_healthy(buy_ex) or not monitor.is_healthy(sell_ex)
            )
            result.append(d)
        return result

    return await asyncio.to_thread(_query)
