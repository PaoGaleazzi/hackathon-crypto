from __future__ import annotations

import asyncio

from fastapi import APIRouter

from db.connection import get_connection

router = APIRouter(tags=["trades"])

_COLS = [
    "id", "opportunity_id", "buy_exchange", "sell_exchange",
    "qty", "buy_price", "sell_price", "fee_buy", "fee_sell",
    "slippage_est", "net_profit", "status",
    "ws_received_at", "decision_at", "latency_ms", "executed_at",
]


@router.get("/trades")
async def list_trades() -> list[dict]:
    def _query() -> list[dict]:
        rows = get_connection().execute("""
            SELECT id, opportunity_id, buy_exchange, sell_exchange,
                   qty, buy_price, sell_price, fee_buy, fee_sell,
                   slippage_est, net_profit, status,
                   ws_received_at, decision_at, latency_ms, executed_at
            FROM trades
            ORDER BY executed_at DESC
            LIMIT 50
        """).fetchall()
        return [dict(zip(_COLS, row)) for row in rows]

    return await asyncio.to_thread(_query)


@router.get("/pnl")
async def get_pnl() -> dict:
    def _query() -> dict:
        row = get_connection().execute("""
            SELECT
                COALESCE(SUM(net_profit), 0.0)  AS cumulative_pnl_usd,
                COUNT(*)                         AS trade_count
            FROM trades
            WHERE status = 'EXECUTED'
        """).fetchone()
        if row is None:
            return {"cumulative_pnl_usd": 0.0, "trade_count": 0}
        return {"cumulative_pnl_usd": row[0], "trade_count": row[1]}

    return await asyncio.to_thread(_query)
