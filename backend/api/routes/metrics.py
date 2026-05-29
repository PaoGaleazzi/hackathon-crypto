from __future__ import annotations

import asyncio

from fastapi import APIRouter

import data.bbo_state as bbo_state
from core.circuit_breaker import get_circuit_breaker
from db.connection import get_connection

router = APIRouter(tags=["metrics"])


@router.get("/metrics/summary")
async def get_summary_metrics() -> dict:
    def _query() -> dict:
        conn = get_connection()

        pnl_row = conn.execute("""
            SELECT
                COALESCE(SUM(net_profit), 0.0) AS total_pnl,
                COUNT(*) FILTER (WHERE executed_at::date = current_date) AS count_today,
                COALESCE(MAX(net_profit), 0.0) AS best_spread_usd
            FROM trades
            WHERE status = 'EXECUTED'
        """).fetchone()

        return {
            "total_pnl_usd": pnl_row[0],
            "trade_count_today": pnl_row[1],
            "best_spread_usd": pnl_row[2],
        }

    return await asyncio.to_thread(_query)


@router.get("/metrics/latency")
async def get_latency_metrics() -> dict:
    def _query() -> dict:
        conn = get_connection()

        # Prefer latency_events (full WS→decision pipeline); fall back to trades.latency_ms
        count_row = conn.execute("SELECT COUNT(*) FROM latency_events").fetchone()
        if count_row is None or count_row[0] == 0:
            return {"p50_ms": 0, "p95_ms": 0, "p99_ms": 0, "sample_count": 0}

        row = conn.execute("""
            SELECT
                quantile_cont(latency_ms, 0.50) AS p50,
                quantile_cont(latency_ms, 0.95) AS p95,
                quantile_cont(latency_ms, 0.99) AS p99,
                COUNT(*) AS sample_count
            FROM latency_events
        """).fetchone()
        if row is None or row[0] is None:
            return {"p50_ms": 0, "p95_ms": 0, "p99_ms": 0, "sample_count": 0}

        return {
            "p50_ms": row[0],
            "p95_ms": row[1],
            "p99_ms": row[2],
            "sample_count": row[3],
        }

    return await asyncio.to_thread(_query)


@router.get("/status")
async def get_status() -> dict:
    cb = get_circuit_breaker()
    return {
        "circuit_breaker": cb.state.value,
        "circuit_breaker_detail": cb.as_dict(),
        "exchanges_connected": bbo_state.get_connected(),
        "uptime_s": 0,
    }
